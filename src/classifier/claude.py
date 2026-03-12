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
        traffic_management_type=(
            object_data.get("traffic_management_type")
            or object_data.get("traffic_management_type_ref", "Unknown")
        ),
        proposed_start_date=(
            object_data.get("proposed_start_date")
            or object_data.get("start_date", "Unknown")
        ),
        proposed_end_date=(
            object_data.get("proposed_end_date")
            or object_data.get("end_date", "Unknown")
        ),
        work_category=(
            object_data.get("work_category")
            or object_data.get("activity_type_details", "Unknown")
        ),
        promoter_organisation=(
            object_data.get("promoter_organisation")
            or object_data.get("highway_authority", "Unknown")
        ),
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


_DISRUPTION_PROMPT = """You are helping a cycling advocacy group understand the impact of traffic disruptions.

Given this TfL disruption, write a 1-2 sentence summary of how it affects people cycling in the area. Consider: whether the road is a common cycling route, whether diversions are available, and whether the disruption creates danger for cyclists.

Location: {location}
Borough: {borough}
Category: {category}
Status: {status}
Severity: {severity}
Description: {comments}
Corridors: {corridors}
Duration: {start} to {end}

Reply with ONLY the summary, no preamble."""


async def get_disruption_cycling_summary(disruption: dict, borough: str) -> str | None:
    """Generate a Claude-powered cycling impact summary for a TfL disruption."""
    if not settings.anthropic_api_key:
        return None

    corridors = disruption.get("corridors", []) or []
    corridor_names = ", ".join(
        c.get("name", "") for c in corridors if isinstance(c, dict)
    ) if corridors else "N/A"

    prompt = _DISRUPTION_PROMPT.format(
        location=disruption.get("location", "Unknown"),
        borough=borough,
        category=disruption.get("category", "Unknown"),
        status=disruption.get("status", "Unknown"),
        severity=disruption.get("severity", "Unknown"),
        comments=(disruption.get("comments", "") or "")[:500],
        corridors=corridor_names,
        start=disruption.get("startDateTime", "Unknown"),
        end=disruption.get("endDateTime", "Unknown"),
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
        logger.exception("Claude disruption classification failed")
        return None


_TRAFFIC_ORDER_PROMPT = """You are helping a cycling advocacy group understand the impact of traffic regulation orders.

Given this traffic order (D-TRO), write a 1-2 sentence summary of how it affects people cycling in the area. Consider: whether it changes road access, creates new restrictions, affects cycle lanes or routes, or changes parking/loading in ways that affect cycling space.

Order name: {tro_name}
Borough: {borough}
Regulation types: {regulation_types}
Streets: {streets}
Action: {action_type}
Description: {description}
Effective: {effective_date}
End date: {end_date}

Reply with ONLY the summary, no preamble."""


async def get_traffic_order_cycling_summary(details: dict, borough: str) -> str | None:
    """Generate a Claude-powered cycling impact summary for a traffic order."""
    if not settings.anthropic_api_key:
        return None

    streets = ", ".join(details.get("street_names", [])) or "Not specified"
    reg_types = ", ".join(details.get("regulation_types", [])) or "Unknown"

    prompt = _TRAFFIC_ORDER_PROMPT.format(
        tro_name=details.get("tro_name", "Unknown"),
        borough=borough,
        regulation_types=reg_types,
        streets=streets,
        action_type=details.get("action_type", "Unknown"),
        description=details.get("provision_description", ""),
        effective_date=details.get("effective_date", "Unknown"),
        end_date=details.get("regulation_end", "Not specified"),
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
        logger.exception("Claude traffic order classification failed")
        return None
