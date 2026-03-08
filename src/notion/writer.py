"""Notion database operations — upsert roadwork records with deduplication."""

from __future__ import annotations

import asyncio
import logging
from notion_client import AsyncClient

from src.config import settings

logger = logging.getLogger(__name__)


class NotionWriter:
    """Writes and updates roadwork records in a Notion database.

    Uses permit_reference_number as the dedup key. Maintains an in-memory
    cache of permit_ref -> page_id mappings, backed by Notion queries
    for cache misses or after restarts.
    """

    def __init__(self) -> None:
        self._client = AsyncClient(auth=settings.notion_api_key)
        self._db_id = settings.notion_roadworks_db_id
        # In-memory cache: permit_reference -> notion page_id
        self._cache: dict[str, str] = {}
        self._cache_warmed = False

    async def warm_cache(self) -> None:
        """Pre-populate the cache by querying all active works from Notion.

        Called once at startup to avoid cold-start Notion queries for every item.
        """
        logger.info("Warming permit reference cache from Notion...")
        try:
            count = 0
            has_more = True
            start_cursor = None

            while has_more:
                query_params = {
                    "database_id": self._db_id,
                    "page_size": 100,
                }
                if start_cursor:
                    query_params["start_cursor"] = start_cursor

                response = await self._client.databases.query(**query_params)

                for page in response["results"]:
                    permit_ref = self._extract_permit_ref(page)
                    if permit_ref:
                        self._cache[permit_ref] = page["id"]
                        count += 1

                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")

            self._cache_warmed = True
            logger.info("Cache warmed with %d permit references", count)

        except Exception:
            logger.exception("Failed to warm cache — will use per-item queries")

    def _extract_permit_ref(self, page: dict) -> str | None:
        """Extract permit reference from a Notion page's properties."""
        prop = page.get("properties", {}).get("Permit Reference", {})
        rich_text = prop.get("rich_text", [])
        if rich_text:
            return rich_text[0].get("text", {}).get("content", "")
        return None

    async def find_by_permit_reference(self, permit_ref: str) -> str | None:
        """Look up a Notion page ID by permit reference.

        Checks the in-memory cache first, falls back to a Notion query.
        """
        if permit_ref in self._cache:
            return self._cache[permit_ref]

        try:
            response = await self._client.databases.query(
                database_id=self._db_id,
                filter={
                    "property": "Permit Reference",
                    "rich_text": {"equals": permit_ref},
                },
                page_size=1,
            )

            if response["results"]:
                page_id = response["results"][0]["id"]
                self._cache[permit_ref] = page_id
                return page_id

        except Exception:
            logger.exception("Notion query failed for permit ref: %s", permit_ref)

        return None

    async def upsert_roadwork(self, permit_ref: str, properties: dict) -> str | None:
        """Create or update a roadwork record in Notion.

        Args:
            permit_ref: The permit reference number (dedup key).
            properties: Notion property values from schemas.work_to_notion_properties().

        Returns:
            The Notion page ID, or None on failure.
        """
        page_id = await self.find_by_permit_reference(permit_ref)

        try:
            if page_id:
                # Update existing page
                await self._client.pages.update(
                    page_id=page_id,
                    properties=properties,
                )
                logger.info("Updated Notion page %s for %s", page_id, permit_ref)
                return page_id
            else:
                # Create new page
                response = await self._client.pages.create(
                    parent={"database_id": self._db_id},
                    properties=properties,
                )
                new_page_id = response["id"]
                self._cache[permit_ref] = new_page_id
                logger.info("Created Notion page %s for %s", new_page_id, permit_ref)
                return new_page_id

        except Exception:
            logger.exception("Notion upsert failed for %s", permit_ref)
            # Simple rate-limit backoff
            await asyncio.sleep(1)
            return None
