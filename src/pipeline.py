"""Core processing pipeline: geo-filter → classify → write to Notion."""

import logging

from src.geo.filter import GeoFilter, parse_bng_wkt_to_wgs84
from src.classifier.rules import quick_cycling_impact
from src.classifier.claude import get_cycling_summary
from src.notion.schemas import work_to_notion_properties
from src.notion.writer import NotionWriter

logger = logging.getLogger(__name__)


class Pipeline:
    """Processes Street Manager notifications through the full pipeline."""

    def __init__(self, geo_filter: GeoFilter, notion_writer: NotionWriter) -> None:
        self._geo_filter = geo_filter
        self._notion_writer = notion_writer

    async def process_notification(self, notification: dict) -> None:
        """Process a single Street Manager SNS notification.

        Steps:
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

        # Step 1: Geo-filter
        include, borough = self._geo_filter.check(object_data)
        if not include:
            logger.debug("Filtered out: not in target boroughs")
            return

        permit_ref = object_data.get("permit_reference_number", "")
        if not permit_ref:
            # Activities and Section 58s may not have permit references
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

        # Step 3: Optional Claude enrichment for high/medium impact
        cycling_summary = None
        if cycling_impact in ("high", "medium"):
            cycling_summary = await get_cycling_summary(object_data, borough)

        # Get WGS84 coordinates for reference
        wgs84_coords = None
        coords_wkt = object_data.get("works_location_coordinates")
        if coords_wkt:
            point = parse_bng_wkt_to_wgs84(coords_wkt)
            if point:
                wgs84_coords = f"{point.x:.6f},{point.y:.6f}"

        # Step 4: Build Notion properties and upsert
        properties = work_to_notion_properties(
            object_data=object_data,
            borough=borough,
            cycling_impact=cycling_impact,
            cycling_summary=cycling_summary,
            event_type=event_type,
            wgs84_coords=wgs84_coords,
        )

        await self._notion_writer.upsert_roadwork(permit_ref, properties)
