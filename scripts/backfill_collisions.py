"""Backfill STATS19 cycling collision data into PostgreSQL.

Usage:
    python -m scripts.backfill_collisions [--year 2024] [--last5]

Downloads STATS19 data from DfT, filters to cyclist collisions in target
boroughs, and writes to the PostgreSQL database.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.db.schemas import collision_to_db_row
from src.db.writer import DatabaseWriter
from src.geo.boundaries import load_borough_polygons
from src.geo.filter import GeoFilter
from src.stats19.importer import import_collisions

logger = logging.getLogger(__name__)


async def main(year: int | None, use_last5: bool) -> None:
    if not settings.database_url:
        logger.error("DATABASE_URL not configured")
        return

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

    db_writer = DatabaseWriter(settings.database_url)
    await db_writer.connect()

    created = 0
    failed = 0

    for i, collision in enumerate(collisions):
        db_row = collision_to_db_row(collision)
        result = await db_writer.upsert_collision(collision.collision_index, db_row)
        if result:
            created += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0:
            logger.info("Progress: %d/%d (created=%d, failed=%d)",
                        i + 1, len(collisions), created, failed)

    await db_writer.close()

    logger.info(
        "Done. Created %d, failed %d (total %d)",
        created, failed, len(collisions),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill STATS19 cycling collision data")
    parser.add_argument("--year", type=int, help="Specific year to import (e.g. 2024)")
    parser.add_argument("--last5", action="store_true", help="Import last 5 years of data")
    args = parser.parse_args()

    if not args.year:
        args.last5 = True

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(main(args.year, args.last5))
