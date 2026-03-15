"""D-TRO processing pipeline: search → fetch full records → classify → PostgreSQL.

Can be run as a one-off backfill (all existing D-TROs) or as an incremental
poll (using the /events endpoint with a `since` timestamp).
"""

from __future__ import annotations

import logging
import re

from src.classifier.claude import get_traffic_order_cycling_summary
from src.config import BOROUGH_SWA_CODES
from src.db.schemas import traffic_order_to_db_row
from src.db.writer import DatabaseWriter
from src.dtro.client import DtroClient
from src.geo.cycling_infrastructure import CyclingInfrastructureIndex
from src.geo.filter import parse_bng_wkt_to_wgs84

logger = logging.getLogger(__name__)

# SWA code → borough name, including TfL
_TRA_TO_BOROUGH: dict[int, str] = {int(k): v for k, v in BOROUGH_SWA_CODES.items()}
_TRA_TO_BOROUGH[20] = "Transport for London"

# Regulation types that are directly relevant to cycling
_HIGH_IMPACT_REGULATIONS = {
    "miscRoadClosure",
    "miscCycleLaneClosure",
    "miscOneWay",
}

_MEDIUM_IMPACT_REGULATIONS = {
    "miscSuspensionOfParkingRestriction",
    "speedLimit",
    "miscBusLane",
    "kerbsideLoadingPlace",
}

_POSITIVE_REGULATIONS = {
    "cycleLane",
}


def classify_traffic_order_impact(regulation_types: list[str], action_type: str) -> str:
    """Classify cycling impact of a traffic order.

    Returns one of: "Positive", "Negative", "Neutral", "Needs Review".
    """
    reg_set = set(regulation_types)

    # New cycle lane = positive
    if reg_set & _POSITIVE_REGULATIONS:
        return "Positive"

    # Revocations of cycle-positive regs = negative
    if action_type == "revocation" and reg_set & _POSITIVE_REGULATIONS:
        return "Negative"

    # Road closures and cycle lane closures = negative
    if reg_set & _HIGH_IMPACT_REGULATIONS:
        return "Negative"

    # Parking/loading changes might affect cycling
    if reg_set & _MEDIUM_IMPACT_REGULATIONS:
        return "Needs Review"

    # Parking-only orders are generally neutral for cycling
    parking_regs = {
        "kerbsideNoWaiting", "kerbsideParkingPlace", "kerbsidePermitParkingPlace",
        "kerbsideDisabledBadgeHoldersOnly", "kerbsideTaxiRank",
    }
    if reg_set and reg_set <= parking_regs:
        return "Neutral"

    return "Needs Review"


def extract_dtro_details(full_dtro: dict) -> dict:
    """Extract key fields from a full D-TRO record.

    Returns a flat dict with the fields needed for traffic_order_to_db_row.
    """
    source = full_dtro.get("data", {}).get("source", {})
    provisions = source.get("provision", [])

    # Collect all regulation types across provisions
    regulation_types: list[str] = []
    street_names: list[str] = []
    coordinates: str | None = None

    for provision in provisions:
        for reg in provision.get("regulation", []):
            gr = reg.get("generalRegulation", {})
            rt = gr.get("regulationType")
            if rt and rt not in regulation_types:
                regulation_types.append(rt)

        # Extract street names and coordinates from regulated places
        for place in provision.get("regulatedPlace", []):
            # Only use regulationLocation places (not diversion routes)
            if place.get("type") != "regulationLocation":
                continue

            desc = place.get("description", "")
            if desc and desc not in street_names:
                # Clean up descriptions like "CRESSINGHAM ROAD - side of road: south"
                clean = re.sub(r"\s*-\s*side of road:.*$", "", desc)
                if clean and clean not in street_names:
                    street_names.append(clean)

            # Extract first available coordinates (BNG LINESTRING)
            if not coordinates:
                geom = place.get("linearGeometry", {})
                linestring = geom.get("linestring", "")
                if linestring:
                    # Extract WGS84 point from BNG linestring
                    point = parse_bng_wkt_to_wgs84(linestring)
                    if point:
                        coordinates = f"{point.x:.6f},{point.y:.6f}"

    # Collect regulation start/end times from search result or provision conditions
    reg_start = None
    reg_end = None
    for provision in provisions:
        for reg in provision.get("regulation", []):
            for cond in reg.get("condition", []):
                tv = cond.get("timeValidity", {})
                if tv.get("start") and not reg_start:
                    reg_start = tv["start"]
                if tv.get("end") and not reg_end:
                    reg_end = tv["end"]

    return {
        "dtro_id": full_dtro.get("id", ""),
        "tro_name": source.get("troName", ""),
        "reference": source.get("reference", ""),
        "tra_name": full_dtro.get("traName", ""),
        "tra_code": source.get("traCreator", 0),
        "action_type": source.get("actionType", ""),
        "made_date": source.get("madeDate"),
        "effective_date": source.get("comingIntoForceDate"),
        "regulation_types": regulation_types,
        "street_names": street_names,
        "coordinates": coordinates,
        "schema_version": full_dtro.get("schemaVersion", ""),
        "regulation_start": reg_start,
        "regulation_end": reg_end,
        "provision_description": (
            provisions[0].get("provisionDescription", "") if provisions else ""
        ),
    }


async def poll_traffic_orders(
    db_writer: DatabaseWriter,
    cid_index: CyclingInfrastructureIndex | None = None,
) -> int:
    """Fetch all D-TROs from target boroughs and write to PostgreSQL.

    Returns the number of records processed.
    """
    dtro_client = DtroClient()

    # Search for all D-TROs from target boroughs
    search_results = await dtro_client.search_all_boroughs()
    logger.info("Found %d D-TROs from target boroughs", len(search_results))

    processed = 0
    created = 0
    failed = 0

    for item in search_results:
        dtro_id = item.get("id")
        if not dtro_id:
            continue

        try:
            # Fetch full D-TRO record
            full_dtro = await dtro_client.get_dtro(dtro_id)
            details = extract_dtro_details(full_dtro)

            # Determine borough from TRA code
            tra_code = details["tra_code"]
            borough = _TRA_TO_BOROUGH.get(tra_code, "Unknown")

            # Classify cycling impact
            cycling_impact = classify_traffic_order_impact(
                details["regulation_types"], details["action_type"]
            )

            # CID proximity check: upgrade Neutral → Needs Review if near cycling infra
            cid_description = None
            if cid_index and details.get("coordinates"):
                coords = details["coordinates"]
                try:
                    lon, lat = (float(c) for c in coords.split(","))
                    from shapely.geometry import Point
                    cid_result = cid_index.check_proximity(Point(lon, lat))
                    if cid_result:
                        cid_description = cid_result.format_notion()
                        if cycling_impact == "Neutral":
                            cycling_impact = "Needs Review"
                except (ValueError, TypeError):
                    pass

            # Optional Claude summary for negative/needs review
            cycling_summary = None
            if cycling_impact in ("Negative", "Needs Review"):
                cycling_summary = await get_traffic_order_cycling_summary(
                    details, borough
                )

            # Write to PostgreSQL
            db_row = traffic_order_to_db_row(
                details=details,
                borough=borough,
                cycling_impact=cycling_impact,
                cycling_summary=cycling_summary,
                nearby_cycling_infra=cid_description,
            )
            result = await db_writer.upsert_traffic_order(dtro_id, db_row)
            if result:
                created += 1
            else:
                failed += 1

            processed += 1
            if processed % 20 == 0:
                logger.info(
                    "D-TRO progress: %d/%d (created=%d, failed=%d)",
                    processed, len(search_results), created, failed,
                )

        except Exception:
            logger.exception("Failed to process D-TRO %s", dtro_id)
            failed += 1

    logger.info(
        "D-TRO done. Created %d, failed %d (total %d)",
        created, failed, len(search_results),
    )
    return processed
