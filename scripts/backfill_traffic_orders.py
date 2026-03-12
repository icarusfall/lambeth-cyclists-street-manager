"""Backfill D-TRO traffic orders into Notion.

Usage:
    python -m scripts.backfill_traffic_orders

Searches the D-TRO API for all traffic orders from target boroughs,
fetches full records, classifies cycling impact, and writes to the
Notion Traffic Orders database.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dtro.pipeline import poll_traffic_orders
from src.notion.writer import NotionWriter

logger = logging.getLogger(__name__)


async def main() -> None:
    notion_writer = NotionWriter()
    await notion_writer.warm_traffic_orders_cache()

    count = await poll_traffic_orders(notion_writer)
    logger.info("Backfill complete. Processed %d traffic orders.", count)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
