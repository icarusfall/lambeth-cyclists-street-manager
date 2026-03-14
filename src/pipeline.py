"""Core processing pipeline: geo-filter → classify → write to Notion."""

import logging

from src.geo.filter import GeoFilter, parse_bng_wkt_to_wgs84
from src.geo.cycling_infrastructure import CyclingInfrastructureIndex
from src.classifier.rules import quick_cycling_impact, upgrade_impact_with_cid
from src.classifier.claude import get_cycling_summary
from src.notion.schemas import work_to_notion_properties
from src.notion.writer import NotionWriter

logger = logging.getLogger(__name__)


def _normalise_activity_data(notification: dict) -> None:
    """Normalise activity event fields to permit-equivalent names.

    Activity events (from the prod-activity-topic) use different field names
    than permit events. This maps them so downstream code works for both.
    Modifies object_data in-place.
    """
    event_type = notification.get("event_type", "")
    if not event_type.startswith("ACTIVITY_"):
        return

    od = notification.get("object_data", {})

    # Reference number
    if "activity_reference_number" in od and "permit_reference_number" not in od:
        od["permit_reference_number"] = od["activity_reference_number"]

    # Coordinates (can be POINT or LINESTRING)
    if "activity_coordinates" in od and "works_location_coordinates" not in od:
        od["works_location_coordinates"] = od["activity_coordinates"]

    # Dates
    if "start_date" in od and "proposed_start_date" not in od:
        od["proposed_start_date"] = od["start_date"]
    if "end_date" in od and "proposed_end_date" not in od:
        od["proposed_end_date"] = od["end_date"]

    # Location type
    if "activity_location_type" in od and "works_location_type" not in od:
        od["works_location_type"] = od["activity_location_type"]

    # Traffic management — activities have the raw value directly
    if "traffic_management_type" in od and "traffic_management_type_ref" not in od:
        od["traffic_management_type_ref"] = od["traffic_management_type"]

    # Cancelled status → work_status_ref
    if od.get("cancelled") == "Yes" and "work_status_ref" not in od:
        od["work_status_ref"] = "cancelled"


class Pipeline:
    """Processes Street Manager notifications through the full pipeline."""

    def __init__(
        self,
        geo_filter: GeoFilter,
        notion_writer: NotionWriter,
        cid_index: CyclingInfrastructureIndex | None = None,
    ) -> None:
        self._geo_filter = geo_filter
        self._notion_writer = notion_writer
        self._cid_index = cid_index

    async def process_notification(self, notification: dict) -> None:
        """Process a single Street Manager SNS notification.

        Steps:
        0. Normalise activity fields to permit equivalents
        1. Geo-filter: is this work in one of our target boroughs?
        2. Classify cycling impact (rule-based)
        3. Optionally get Claude summary for high/medium impact
        4. Upsert to Notion
        """
        event_type = notification.get("event_type", "")
        object_data = notification.get("object_data", {})

        if not object_data:
            logger.warning("Notification has no object_data, skipping")
            return

        # Step 0: Normalise activity fields
        _normalise_activity_data(notification)

        # Step 1: Geo-filter
        include, borough = self._geo_filter.check(object_data)
        if not include:
            return

        permit_ref = object_data.get("permit_reference_number", "")
        if not permit_ref:
            permit_ref = notification.get("object_reference", "")
        if not permit_ref:
            logger.warning("No permit/object reference found, skipping")
            return

        logger.info(
            "Processing %s on %s (%s) — %s",
            event_type,
            object_data.get("street_name", "unknown"),
            borough,
            permit_ref,
        )

        # Step 2: Rule-based cycling impact classification
        cycling_impact = quick_cycling_impact(object_data)

        # Get WGS84 coordinates for reference and CID lookup
        wgs84_coords = None
        cid_description = None
        coords_wkt = object_data.get("works_location_coordinates")
        if coords_wkt:
            point = parse_bng_wkt_to_wgs84(coords_wkt)
            if point:
                wgs84_coords = f"{point.x:.6f},{point.y:.6f}"

                # Step 2b: Upgrade impact if near cycling infrastructure
                if self._cid_index:
                    cid_result = self._cid_index.check_proximity(point)
                    if cid_result:
                        cycling_impact = upgrade_impact_with_cid(cycling_impact, cid_result)
                        cid_description = cid_result.format_notion()

        # Step 3: Optional Claude enrichment for high/medium impact
        cycling_summary = None
        if cycling_impact in ("high", "medium"):
            cycling_summary = await get_cycling_summary(object_data, borough)

        # Step 4: Build Notion properties and upsert
        properties = work_to_notion_properties(
            object_data=object_data,
            borough=borough,
            cycling_impact=cycling_impact,
            cycling_summary=cycling_summary,
            event_type=event_type,
            wgs84_coords=wgs84_coords,
            nearby_cycling_infra=cid_description,
        )

        await self._notion_writer.upsert_roadwork(permit_ref, properties)
