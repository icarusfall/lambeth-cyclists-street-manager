"""Backfill D-TRO traffic orders into PostgreSQL.

Usage:
    python -m scripts.backfill_traffic_orders

Searches the D-TRO API for all traffic orders from target boroughs,
fetches full records, classifies cycling impact, and writes to PostgreSQL.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.db.writer import DatabaseWriter
from src.dtro.pipeline import poll_traffic_orders

logger = logging.getLogger(__name__)


async def main() -> None:
    if not settings.database_url:
        logger.error("DATABASE_URL not configured")
        return

    db_writer = DatabaseWriter(settings.database_url)
    await db_writer.connect()

    count = await poll_traffic_orders(db_writer)

    await db_writer.close()
    logger.info("Backfill complete. Processed %d traffic orders.", count)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
