"""Map data to flat dicts for PostgreSQL INSERT/UPDATE."""

import datetime as _dt


def _parse_date(value: str | None) -> _dt.date | None:
    """Parse an ISO date string to a date object, or None."""
    if not value:
        return None
    try:
        dt = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.date()
    except (ValueError, TypeError):
        return None


def _parse_datetime(value: str | None) -> _dt.datetime | None:
    """Parse an ISO datetime string to a datetime object, or None."""
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _parse_bool(value) -> bool:
    return str(value).lower() in ("yes", "true", "1")


def _parse_coords(wgs84_coords: str | None) -> tuple[float | None, float | None]:
    """Split "lon,lat" string into (lon, lat) floats."""
    if not wgs84_coords:
        return None, None
    try:
        parts = wgs84_coords.split(",")
        return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return None, None


# Human-readable labels for field values
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

_WORK_CATEGORY_LABELS = {
    "major": "Major",
    "standard": "Standard",
    "minor": "Minor",
    "immediate_urgent": "Immediate Urgent",
    "immediate_emergency": "Immediate Emergency",
}

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


def work_to_db_row(
    object_data: dict,
    borough: str,
    cycling_impact: str,
    cycling_summary: str | None,
    event_type: str,
    wgs84_coords: str | None = None,
    nearby_cycling_infra: str | None = None,
) -> dict:
    """Convert Street Manager work data to a flat dict for PostgreSQL."""
    street = object_data.get("street_name", "Unknown street")
    area = object_data.get("area_name", "") or object_data.get("town", "")
    name = f"{street}, {area}" if area else street

    tm_ref = (
        object_data.get("traffic_management_type_ref")
        or object_data.get("traffic_management_type", "")
    )
    cat_ref = object_data.get("work_category_ref", "")
    status_ref = object_data.get("work_status_ref", "")

    permit_ref = (
        object_data.get("permit_reference_number")
        or object_data.get("activity_reference_number", "")
    )
    work_ref = object_data.get("work_reference_number", "")

    start_date = object_data.get("proposed_start_date") or object_data.get("start_date")
    end_date = object_data.get("proposed_end_date") or object_data.get("end_date")

    lon, lat = _parse_coords(wgs84_coords)

    return {
        "permit_reference": permit_ref,
        "name": name,
        "work_reference": work_ref,
        "borough": borough,
        "highway_authority": object_data.get("highway_authority", ""),
        "street_name": street,
        "area": area,
        "usrn": object_data.get("usrn", ""),
        "promoter": object_data.get("promoter_organisation", ""),
        "work_category": _WORK_CATEGORY_LABELS.get(cat_ref, cat_ref or "Unknown"),
        "traffic_management": _TRAFFIC_MGMT_LABELS.get(tm_ref, tm_ref or "Unknown"),
        "work_status": _WORK_STATUS_LABELS.get(status_ref, status_ref or "Unknown"),
        "proposed_start": _parse_date(start_date),
        "proposed_end": _parse_date(end_date),
        "actual_start": _parse_date(object_data.get("actual_start_date_time")),
        "ttro_required": _parse_bool(
            object_data.get("is_ttro_required")
            or object_data.get("traffic_management_required", "No")
        ),
        "cycling_impact": cycling_impact.capitalize(),
        "cycling_summary": cycling_summary,
        "activity_type": object_data.get("activity_type", ""),
        "source_event": event_type,
        "nearby_cycling_infra": nearby_cycling_infra,
        "lon": lon,
        "lat": lat,
    }


def disruption_to_db_row(
    disruption: dict,
    borough: str,
    cycling_impact: str,
    cycling_summary: str | None = None,
    wgs84_coords: str | None = None,
    nearby_cycling_infra: str | None = None,
) -> dict:
    """Convert a TfL disruption to a flat dict for PostgreSQL."""
    location = disruption.get("location", "Unknown location")
    category = disruption.get("category", "Other")
    name = f"{location} — {category}"

    status = disruption.get("status", "Active")
    corridors_list = disruption.get("corridors", []) or []
    corridors = ", ".join(
        c.get("name", "") for c in corridors_list if isinstance(c, dict)
    ) if corridors_list else ""

    lon, lat = _parse_coords(wgs84_coords)

    return {
        "disruption_id": str(disruption.get("id", "")),
        "name": name,
        "borough": borough,
        "category": _DISRUPTION_CATEGORY_LABELS.get(category, category or "Other"),
        "sub_category": disruption.get("subCategory", ""),
        "status": _DISRUPTION_STATUS_LABELS.get(status, status or "Active"),
        "severity": disruption.get("severity", ""),
        "location_desc": location,
        "corridors": corridors,
        "start_time": _parse_datetime(disruption.get("startDateTime")),
        "end_time": _parse_datetime(disruption.get("endDateTime")),
        "description": (disruption.get("comments", "") or "")[:2000],
        "cycling_impact": cycling_impact.capitalize(),
        "cycling_summary": cycling_summary,
        "nearby_cycling_infra": nearby_cycling_infra,
        "lon": lon,
        "lat": lat,
    }


def collision_to_db_row(collision) -> dict:
    """Convert a CyclistCollision dataclass to a flat dict for PostgreSQL."""
    road = collision.road_name or "Unknown road"
    name = f"{road} — {collision.date}"

    # Parse STATS19 DD/MM/YYYY date
    date_val = None
    try:
        date_val = _dt.datetime.strptime(collision.date, "%d/%m/%Y").date()
    except (ValueError, TypeError):
        pass

    return {
        "collision_reference": collision.collision_index,
        "name": name,
        "borough": collision.borough,
        "date": date_val,
        "time": collision.time,
        "severity": collision.collision_severity,
        "number_of_cyclists_hurt": collision.num_cyclist_casualties,
        "worst_cyclist_severity": collision.worst_cyclist_severity,
        "other_vehicles": (
            ", ".join(collision.other_vehicles) if collision.other_vehicles else "None"
        ),
        "road_name": road,
        "speed_limit": collision.speed_limit,
        "junction_detail": collision.junction_detail,
        "light_conditions": collision.light_conditions,
        "weather": collision.weather,
        "road_surface": collision.road_surface,
        "data_year": collision.data_year,
        "lon": collision.longitude,
        "lat": collision.latitude,
    }


def traffic_order_to_db_row(
    details: dict,
    borough: str,
    cycling_impact: str,
    cycling_summary: str | None = None,
    nearby_cycling_infra: str | None = None,
) -> dict:
    """Convert D-TRO details to a flat dict for PostgreSQL."""
    street_names = details.get("street_names", [])
    location = ", ".join(street_names) if street_names else ""

    coords = details.get("coordinates")
    lon, lat = _parse_coords(coords)

    return {
        "dtro_id": details.get("dtro_id", ""),
        "name": details.get("tro_name", "Unknown"),
        "dtro_reference": details.get("reference", ""),
        "borough": borough,
        "regulation_type": details.get("regulation_types", []),
        "location_description": details.get("provision_description", "") or location,
        "street_name": location,
        "made_date": _parse_date(details.get("made_date")),
        "effective_date": _parse_date(details.get("effective_date")),
        "end_date": _parse_date(details.get("regulation_end")),
        "authority": details.get("tra_name", ""),
        "action_type": details.get("action_type", "new").capitalize(),
        "cycling_impact": cycling_impact,
        "cycling_summary": cycling_summary,
        "nearby_cycling_infra": nearby_cycling_infra,
        "schema_version": details.get("schema_version", ""),
        "lon": lon,
        "lat": lat,
    }
