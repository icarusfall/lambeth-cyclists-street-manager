"""Optional Claude API enrichment for cycling impact summaries."""

from __future__ import annotations

import logging

import anthropic

from src.config import settings

logger = logging.getLogger(__name__)

_PROMPT = """You are helping a cycling advocacy group understand the impact of roadworks.

Given this roadwork notification, write a 1-2 sentence summary of how it affects people cycling in the area. Consider: whether the road is a common cycling route, whether alternative routes exist, whether the traffic management creates pinch points, and whether temporary arrangements are cycle-friendly.

Street: {street_name}, {area_name}
Borough: {borough}
Work type: {activity_type}
Traffic management: {traffic_management_type}
Duration: {proposed_start_date} to {proposed_end_date}
Category: {work_category}
Promoter: {promoter_organisation}

Reply with ONLY the summary, no preamble."""


async def get_cycling_summary(object_data: dict, borough: str) -> str | None:
    """Generate a Claude-powered cycling impact summary.

    Only called for high/medium impact works. Returns None if the API key
    is not configured or the call fails.
    """
    if not settings.anthropic_api_key:
        return None

    prompt = _PROMPT.format(
        street_name=object_data.get("street_name", "Unknown"),
        area_name=object_data.get("area_name", ""),
        borough=borough,
        activity_type=object_data.get("activity_type", "Unknown"),
        traffic_management_type=object_data.get("traffic_management_type", "Unknown"),
        proposed_start_date=object_data.get("proposed_start_date", "Unknown"),
        proposed_end_date=object_data.get("proposed_end_date", "Unknown"),
        work_category=object_data.get("work_category", "Unknown"),
        promoter_organisation=object_data.get("promoter_organisation", "Unknown"),
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        logger.exception("Claude classification failed")
        return None
