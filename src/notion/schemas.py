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
    nearby_cycling_infra: str | None = None,
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
    area = object_data.get("area_name", "") or object_data.get("town", "")
    title = f"{street}, {area}" if area else street

    # Permits use _ref fields; activities use raw values directly
    tm_ref = (
        object_data.get("traffic_management_type_ref")
        or object_data.get("traffic_management_type", "")
    )
    cat_ref = object_data.get("work_category_ref", "")
    status_ref = object_data.get("work_status_ref", "")

    # Reference numbers — activities use activity_reference_number
    permit_ref = (
        object_data.get("permit_reference_number")
        or object_data.get("activity_reference_number", "")
    )
    work_ref = object_data.get("work_reference_number", "")

    # Dates — activities use start_date/end_date
    start_date = (
        object_data.get("proposed_start_date")
        or object_data.get("start_date")
    )
    end_date = (
        object_data.get("proposed_end_date")
        or object_data.get("end_date")
    )

    props = {
        "Name": _title(title),
        "Permit Reference": _rich_text(permit_ref),
        "Work Reference": _rich_text(work_ref),
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
        "Proposed Start": _date(start_date),
        "Proposed End": _date(end_date),
        "Actual Start": _date(object_data.get("actual_start_date_time")),
        "Cycling Impact": _select(cycling_impact.capitalize()),
        "Activity Type": _rich_text(
            object_data.get("activity_type", "")
        ),
        "TTRO Required": _checkbox(
            object_data.get("is_ttro_required")
            or object_data.get("traffic_management_required", "No")
        ),
        "Last Updated": _date(datetime.utcnow().isoformat()),
        "Source Event": _rich_text(event_type),
    }

    if cycling_summary:
        props["Cycling Summary"] = _rich_text(cycling_summary)

    if wgs84_coords:
        props["Coordinates"] = _rich_text(wgs84_coords)

    if nearby_cycling_infra:
        props["Nearby Cycling Infrastructure"] = _rich_text(nearby_cycling_infra)

    return props


# TfL disruption categories (from live API observation)
_DISRUPTION_CATEGORY_LABELS = {
    "Works": "Works",
    "Collisions": "Collisions",
    "Hazards": "Hazards",
    "Network delays": "Network delays",
    "Asset issues": "Asset issues",
    "Breakdowns": "Breakdowns",
    "Planned events": "Planned events",
}

_DISRUPTION_STATUS_LABELS = {
    "Active": "Active",
    "Scheduled": "Scheduled",
    "Resolved": "Resolved",
}


def disruption_to_notion_properties(
    disruption: dict,
    borough: str,
    cycling_impact: str,
    cycling_summary: str | None = None,
    wgs84_coords: str | None = None,
    nearby_cycling_infra: str | None = None,
) -> dict:
    """Convert a TfL disruption to Notion page properties.

    Args:
        disruption: The disruption dict from the TfL API.
        borough: Matched borough name from geo-filtering.
        cycling_impact: "high", "medium", "low", or "minimal".
        cycling_summary: Claude-generated summary, or None.
        wgs84_coords: Optional "lon,lat" string for reference.

    Returns:
        Dict of Notion property values ready for the API.
    """
    location = disruption.get("location", "Unknown location")
    category = disruption.get("category", "Other")
    title = f"{location} — {category}"

    status = disruption.get("status", "Active")
    sub_category = disruption.get("subCategory", "")
    severity = disruption.get("severity", "")
    comments = disruption.get("comments", "") or ""
    corridors_list = disruption.get("corridors", []) or []
    corridors = ", ".join(
        c.get("name", "") for c in corridors_list if isinstance(c, dict)
    ) if corridors_list else ""

    props = {
        "Name": _title(title),
        "TfL Disruption ID": _rich_text(str(disruption.get("id", ""))),
        "Borough": _select(borough),
        "Category": _select(
            _DISRUPTION_CATEGORY_LABELS.get(category, category or "Other")
        ),
        "Sub-Category": _rich_text(sub_category),
        "Status": _select(
            _DISRUPTION_STATUS_LABELS.get(status, status or "Active")
        ),
        "Severity": _rich_text(severity),
        "Location": _rich_text(location),
        "Corridors": _rich_text(corridors),
        "Start Time": _date(disruption.get("startDateTime")),
        "End Time": _date(disruption.get("endDateTime")),
        "Description": _rich_text(comments[:2000]),
        "Cycling Impact": _select(cycling_impact.capitalize()),
        "Last Updated": _date(datetime.utcnow().isoformat()),
    }

    if cycling_summary:
        props["Cycling Summary"] = _rich_text(cycling_summary)

    if wgs84_coords:
        props["Coordinates"] = _rich_text(wgs84_coords)

    if nearby_cycling_infra:
        props["Nearby Cycling Infrastructure"] = _rich_text(nearby_cycling_infra)

    return props


def _multi_select(values: list[str]) -> dict:
    return {"multi_select": [{"name": v} for v in values]}


def traffic_order_to_notion_properties(
    details: dict,
    borough: str,
    cycling_impact: str,
    cycling_summary: str | None = None,
    nearby_cycling_infra: str | None = None,
) -> dict:
    """Convert D-TRO details to Notion page properties.

    Args:
        details: Flat dict from dtro.pipeline.extract_dtro_details().
        borough: Matched borough name.
        cycling_impact: "Positive", "Negative", "Neutral", or "Needs Review".
        cycling_summary: Claude-generated summary, or None.

    Returns:
        Dict of Notion property values ready for the API.
    """
    tro_name = details.get("tro_name", "Unknown")
    street_names = details.get("street_names", [])
    location = ", ".join(street_names) if street_names else ""

    props = {
        "Name": _title(tro_name),
        "D-TRO ID": _rich_text(details.get("dtro_id", "")),
        "D-TRO Reference": _rich_text(details.get("reference", "")),
        "Borough": _select(borough),
        "Regulation Type": _multi_select(details.get("regulation_types", [])),
        "Location Description": _rich_text(
            details.get("provision_description", "") or location
        ),
        "Street Name": _rich_text(location),
        "Made Date": _date(details.get("made_date")),
        "Effective Date": _date(details.get("effective_date")),
        "Authority": _rich_text(details.get("tra_name", "")),
        "Action Type": _select(details.get("action_type", "new").capitalize()),
        "Cycling Impact": _select(cycling_impact),
        "Schema Version": _rich_text(details.get("schema_version", "")),
        "Last Updated": _date(datetime.utcnow().isoformat()),
    }

    # End date from regulation time validity
    reg_end = details.get("regulation_end")
    if reg_end:
        props["End Date"] = _date(reg_end)

    if cycling_summary:
        props["Cycling Summary"] = _rich_text(cycling_summary)

    coords = details.get("coordinates")
    if coords:
        props["Coordinates"] = _rich_text(coords)

    if nearby_cycling_infra:
        props["Nearby Cycling Infrastructure"] = _rich_text(nearby_cycling_infra)

    return props


def _number(value: int | float) -> dict:
    return {"number": value}


def _parse_stats19_date(date_str: str) -> str:
    """Convert STATS19 DD/MM/YYYY date to ISO format for Notion."""
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return ""


def collision_to_notion_properties(collision) -> dict:
    """Convert a CyclistCollision to Notion page properties.

    Args:
        collision: A CyclistCollision dataclass instance.

    Returns:
        Dict of Notion property values ready for the API.
    """
    road = collision.road_name or "Unknown road"
    title = f"{road} — {collision.date}"

    props = {
        "Name": _title(title),
        "Collision Reference": _rich_text(collision.collision_index),
        "Borough": _select(collision.borough),
        "Date": _date(_parse_stats19_date(collision.date)),
        "Time": _rich_text(collision.time),
        "Severity": _select(collision.collision_severity),
        "Number of Cyclists Hurt": _number(collision.num_cyclist_casualties),
        "Worst Cyclist Severity": _select(collision.worst_cyclist_severity),
        "Other Vehicles": _rich_text(
            ", ".join(collision.other_vehicles) if collision.other_vehicles else "None"
        ),
        "Road Name": _rich_text(road),
        "Speed Limit": _number(collision.speed_limit),
        "Junction Detail": _rich_text(collision.junction_detail),
        "Light Conditions": _select(collision.light_conditions),
        "Weather": _select(collision.weather),
        "Road Surface": _select(collision.road_surface),
        "Coordinates": _rich_text(f"{collision.longitude:.6f},{collision.latitude:.6f}"),
        "Data Year": _rich_text(collision.data_year),
    }

    return props
