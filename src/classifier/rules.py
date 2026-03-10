"""Rule-based cycling impact classification for street works."""

HIGH_IMPACT_TRAFFIC_MGMT = {
    "road_closure",
    "lane_closure",
}

MEDIUM_IMPACT_TRAFFIC_MGMT = {
    "multi_way_signals",
    "two_way_signals",
    "convoy_working",
    "give_and_take",
}

LOW_IMPACT_TRAFFIC_MGMT = {
    "some_carriageway_restriction",
    "no_carriageway_restriction",
}


def quick_cycling_impact(object_data: dict) -> str:
    """Classify cycling impact from Street Manager work data.

    Returns one of: "high", "medium", "low", "minimal".
    """
    # Permits use _ref fields; activities use the raw value directly
    tm = object_data.get("traffic_management_type_ref") or object_data.get("traffic_management_type", "")
    cat = object_data.get("work_category_ref", "")
    loc = object_data.get("works_location_type") or object_data.get("activity_location_type", "")

    # Footway-only works with low traffic management rarely affect cycling
    if loc == "Footway" and tm in LOW_IMPACT_TRAFFIC_MGMT:
        return "minimal"

    if tm in HIGH_IMPACT_TRAFFIC_MGMT:
        return "high"
    elif tm in MEDIUM_IMPACT_TRAFFIC_MGMT:
        return "medium"
    elif cat in ("immediate_urgent", "immediate_emergency"):
        return "medium"  # Emergency works are unpredictable
    else:
        return "low"
