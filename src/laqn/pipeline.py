"""LAQN air quality processing pipeline: fetch daily index → PostgreSQL."""

from __future__ import annotations

import logging
from datetime import datetime

from src.db.writer import DatabaseWriter
from src.laqn.client import BOROUGH_LA_IDS, fetch_daily_index_for_borough

logger = logging.getLogger(__name__)


def _parse_sites(data: dict) -> list[dict]:
    """Extract site readings from LAQN daily index response.

    The API nests data as: DailyAirQualityIndex → LocalAuthority → Site → Species.
    Site can be a single dict or a list of dicts depending on how many sites the borough has.
    """
    la = data.get("DailyAirQualityIndex", {}).get("LocalAuthority")
    if not la:
        return []

    # LocalAuthority can be a single dict or a list
    if isinstance(la, dict):
        la = [la]

    rows = []
    for authority in la:
        borough = authority.get("@LocalAuthorityName", "")
        sites = authority.get("Site", [])
        if isinstance(sites, dict):
            sites = [sites]

        for site in sites:
            site_code = site.get("@SiteCode", "")
            site_name = site.get("@SiteName", "")
            site_type = site.get("@SiteType", "")
            lat = _safe_float(site.get("@Latitude"))
            lon = _safe_float(site.get("@Longitude"))
            bulletin_date = site.get("@BulletinDate", "")

            # Parse reading date from bulletin
            reading_date = None
            if bulletin_date:
                try:
                    reading_date = datetime.strptime(
                        bulletin_date.split(" ")[0], "%Y-%m-%d"
                    ).date()
                except (ValueError, IndexError):
                    pass

            species_list = site.get("Species", [])
            if isinstance(species_list, dict):
                species_list = [species_list]

            for species in species_list:
                index_val = species.get("@AirQualityIndex", "")
                rows.append({
                    "site_code": site_code,
                    "site_name": site_name,
                    "site_type": site_type,
                    "borough": borough,
                    "species_code": species.get("@SpeciesCode", ""),
                    "reading_date": reading_date,
                    "air_quality_index": int(index_val) if index_val.isdigit() else None,
                    "air_quality_band": species.get("@AirQualityBand", ""),
                    "index_source": species.get("@IndexSource", ""),
                    "lon": lon,
                    "lat": lat,
                })

    return rows


def _safe_float(val: str | None) -> float | None:
    if not val:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def poll_air_quality(db_writer: DatabaseWriter) -> int:
    """Fetch daily air quality index for all target boroughs and write to PostgreSQL.

    Returns the number of readings processed.
    """
    processed = 0
    failed = 0

    for la_id, borough_name in BOROUGH_LA_IDS.items():
        try:
            data = await fetch_daily_index_for_borough(la_id)
            rows = _parse_sites(data)

            for row in rows:
                if not row["reading_date"]:
                    continue
                result = await db_writer.upsert_air_quality(row)
                if result:
                    processed += 1
                else:
                    failed += 1

            logger.info(
                "LAQN %s: %d readings fetched", borough_name, len(rows)
            )
        except Exception:
            logger.exception("LAQN fetch failed for %s (LA %d)", borough_name, la_id)
            failed += 1

    logger.info("LAQN done: %d readings upserted, %d failed", processed, failed)
    return processed
