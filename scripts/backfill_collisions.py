"""Backfill STATS19 cycling collision data into Notion.

Usage:
    python -m scripts.backfill_collisions [--year 2024] [--last5]

Downloads STATS19 data from DfT, filters to cyclist collisions in target
boroughs, and writes to the Notion Cycling Collisions database.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.geo.boundaries import load_borough_polygons
from src.geo.filter import GeoFilter
from src.notion.schemas import collision_to_notion_properties
from src.notion.writer import NotionWriter
from src.stats19.importer import import_collisions

logger = logging.getLogger(__name__)


async def main(year: int | None, use_last5: bool) -> None:
    # Load borough boundaries
    geojson_path = Path(__file__).parent.parent / "data" / "london_boroughs.geojson"
    borough_polygons = load_borough_polygons(str(geojson_path), settings.get_target_boroughs())
    geo_filter = GeoFilter(borough_polygons)

    logger.info("Downloading and filtering STATS19 data...")
    collisions = await import_collisions(geo_filter, year=year, use_last5=use_last5)
    logger.info("Found %d cyclist collisions in target boroughs", len(collisions))

    if not collisions:
        logger.info("No collisions to write")
        return

    if not settings.notion_collisions_db_id:
        logger.error("NOTION_COLLISIONS_DB_ID not configured")
        return

    # Write to Notion
    notion_writer = NotionWriter()
    await notion_writer.warm_collisions_cache()

    created = 0
    updated = 0
    failed = 0

    for i, collision in enumerate(collisions):
        properties = collision_to_notion_properties(collision)
        existing = await notion_writer.find_collision(collision.collision_index)

        page_id = await notion_writer.upsert_collision(
            collision.collision_index, properties
        )

        if page_id:
            if existing:
                updated += 1
            else:
                created += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0:
            logger.info("Progress: %d/%d (created=%d, updated=%d, failed=%d)",
                        i + 1, len(collisions), created, updated, failed)

    logger.info(
        "Done. Created %d, updated %d, failed %d (total %d)",
        created, updated, failed, len(collisions),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill STATS19 cycling collision data")
    parser.add_argument("--year", type=int, help="Specific year to import (e.g. 2024)")
    parser.add_argument("--last5", action="store_true", help="Import last 5 years of data")
    args = parser.parse_args()

    if not args.year and not args.last5:
        parser.error("Specify either --year or --last5")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(main(args.year, args.last5))
