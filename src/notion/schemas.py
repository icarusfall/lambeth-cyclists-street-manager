"""Map Street Manager work data to Notion database properties."""

from datetime import datetime


def _rich_text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": str(value)[:2000]}}]}


def _title(value: str) -> dict:
    return {"title": [{"text": {"content": str(value)[:200]}}]}


def _select(value: str) -> dict:
    return {"select": {"name": str(value)}}


def _date(value: str | None) -> dict:
    if not value:
        return {"date": None}
    # Street Manager dates are ISO format — Notion accepts ISO date strings
    try:
        # Parse to validate, then return just the date portion
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return {"date": {"start": dt.date().isoformat()}}
    except (ValueError, TypeError):
        return {"date": None}


def _checkbox(value) -> dict:
    return {"checkbox": str(value).lower() in ("yes", "true", "1")}


# Human-readable labels for traffic management types
_TRAFFIC_MGMT_LABELS = {
    "road_closure": "Road closure",
    "lane_closure": "Lane closure",
    "multi_way_signals": "Multi-way signals",
    "two_way_signals": "Two-way signals",
    "convoy_working": "Convoy working",
    "give_and_take": "Give and take",
    "some_carriageway_restriction": "Some carriageway restriction",
    "no_carriageway_restriction": "No carriageway restriction",
}

# Human-readable labels for work categories
_WORK_CATEGORY_LABELS = {
    "major": "Major",
    "standard": "Standard",
    "minor": "Minor",
    "immediate_urgent": "Immediate Urgent",
    "immediate_emergency": "Immediate Emergency",
}

# Human-readable labels for work status
_WORK_STATUS_LABELS = {
    "planned": "Planned",
    "in_progress": "In progress",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "unattributable": "Unattributable",
    "historical": "Historical",
    "non_notifiable": "Non-notifiable",
    "section_81": "Section 81",
}


def work_to_notion_properties(
    object_data: dict,
    borough: str,
    cycling_impact: str,
    cycling_summary: str | None,
    event_type: str,
    wgs84_coords: str | None = None,
) -> dict:
    """Convert Street Manager work data to Notion page properties.

    Args:
        object_data: The object_data dict from the SNS notification.
        borough: Matched borough name from geo-filtering.
        cycling_impact: "high", "medium", "low", or "minimal".
        cycling_summary: Claude-generated summary, or None.
        event_type: The Street Manager event type (e.g. "WORK_START").
        wgs84_coords: Optional "lon,lat" string for reference.

    Returns:
        Dict of Notion property values ready for the API.
    """
    street = object_data.get("street_name", "Unknown street")
    area = object_data.get("area_name", "")
    title = f"{street}, {area}" if area else street

    tm_ref = object_data.get("traffic_management_type_ref", "")
    cat_ref = object_data.get("work_category_ref", "")
    status_ref = object_data.get("work_status_ref", "")

    props = {
        "Name": _title(title),
        "Permit Reference": _rich_text(
            object_data.get("permit_reference_number", "")
        ),
        "Work Reference": _rich_text(
            object_data.get("work_reference_number", "")
        ),
        "Borough": _select(borough),
        "Highway Authority": _rich_text(
            object_data.get("highway_authority", "")
        ),
        "Street Name": _rich_text(street),
        "Area": _rich_text(area),
        "USRN": _rich_text(object_data.get("usrn", "")),
        "Promoter": _rich_text(
            object_data.get("promoter_organisation", "")
        ),
        "Work Category": _select(
            _WORK_CATEGORY_LABELS.get(cat_ref, cat_ref or "Unknown")
        ),
        "Traffic Management": _select(
            _TRAFFIC_MGMT_LABELS.get(tm_ref, tm_ref or "Unknown")
        ),
        "Work Status": _select(
            _WORK_STATUS_LABELS.get(status_ref, status_ref or "Unknown")
        ),
        "Proposed Start": _date(object_data.get("proposed_start_date")),
        "Proposed End": _date(object_data.get("proposed_end_date")),
        "Actual Start": _date(object_data.get("actual_start_date_time")),
        "Cycling Impact": _select(cycling_impact.capitalize()),
        "Activity Type": _rich_text(
            object_data.get("activity_type", "")
        ),
        "TTRO Required": _checkbox(
            object_data.get("is_ttro_required", "No")
        ),
        "Last Updated": _date(datetime.utcnow().isoformat()),
        "Source Event": _rich_text(event_type),
    }

    if cycling_summary:
        props["Cycling Summary"] = _rich_text(cycling_summary)

    if wgs84_coords:
        props["Coordinates"] = _rich_text(wgs84_coords)

    return props
