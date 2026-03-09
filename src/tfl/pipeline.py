"""TfL disruptions processing pipeline: fetch → geo-filter → classify → Notion."""

from __future__ import annotations

import logging

from src.classifier.claude import get_disruption_cycling_summary
from src.geo.filter import GeoFilter
from src.notion.schemas import disruption_to_notion_properties
from src.notion.writer import NotionWriter
from src.tfl.disruptions import (
    classify_disruption_impact,
    extract_point,
    fetch_disruptions,
)

logger = logging.getLogger(__name__)


async def poll_disruptions(geo_filter: GeoFilter, notion_writer: NotionWriter) -> int:
    """Fetch TfL disruptions, filter, classify, and write to Notion.

    Returns the number of disruptions processed (created or updated).
    """
    disruptions = await fetch_disruptions()
    logger.info("Fetched %d disruptions from TfL API", len(disruptions))

    processed = 0
    active_ids: set[str] = set()

    for disruption in disruptions:
        disruption_id = str(disruption.get("id", ""))
        if not disruption_id:
            continue

        # Geo-filter: check if disruption is in a target borough
        point = extract_point(disruption)
        if point:
            include, borough = geo_filter.check_wgs84_point(point)
        else:
            # No coordinates — skip
            continue

        if not include:
            continue

        active_ids.add(disruption_id)

        # Classify cycling impact
        cycling_impact = classify_disruption_impact(disruption)

        # Optional Claude summary for high/medium
        cycling_summary = None
        if cycling_impact in ("high", "medium"):
            cycling_summary = await get_disruption_cycling_summary(disruption, borough)

        # Build coordinates string
        wgs84_coords = f"{point.x:.6f},{point.y:.6f}" if point else None

        # Build Notion properties and upsert
        properties = disruption_to_notion_properties(
            disruption=disruption,
            borough=borough,
            cycling_impact=cycling_impact,
            cycling_summary=cycling_summary,
            wgs84_coords=wgs84_coords,
        )

        await notion_writer.upsert_disruption(disruption_id, properties)
        processed += 1

    # Mark any cached disruptions that are no longer in the feed as Resolved
    await notion_writer.mark_resolved_disruptions(active_ids)

    logger.info("Processed %d disruptions in target boroughs", processed)
    return processed
