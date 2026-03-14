"""Rule-based cycling impact classification for street works."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.geo.cycling_infrastructure import CIDResult

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


# Impact level ordering for upgrade-only logic
_IMPACT_RANK = {"minimal": 0, "low": 1, "medium": 2, "high": 3}

# Asset types that upgrade to "high"
_HIGH_UPGRADE_ASSETS = {
    "cycleway_route",
    "segregated_cycleway",
    "stepped_cycleway",
    "partially_segregated_cycleway",
}

# Asset types that upgrade to at least "medium"
_MEDIUM_UPGRADE_ASSETS = {
    "mandatory_lane",
    "modal_filter",
    "contraflow_lane",
    "advisory_lane",
}


def upgrade_impact_with_cid(current_impact: str, cid_result: CIDResult | None) -> str:
    """Upgrade cycling impact based on proximity to cycling infrastructure.

    Upgrade-only: CID proximity can increase impact, never decrease it.

    Args:
        current_impact: Current impact level ("high", "medium", "low", "minimal").
        cid_result: Result from CyclingInfrastructureIndex.check_proximity(), or None.

    Returns:
        The (possibly upgraded) impact level.
    """
    if cid_result is None:
        return current_impact

    current_rank = _IMPACT_RANK.get(current_impact, 0)

    if cid_result.asset_type in _HIGH_UPGRADE_ASSETS:
        target_rank = _IMPACT_RANK["high"]
    elif cid_result.asset_type in _MEDIUM_UPGRADE_ASSETS:
        target_rank = _IMPACT_RANK["medium"]
    else:
        # shared_use_path or unknown — no upgrade
        return current_impact

    if target_rank > current_rank:
        # Return the name for the target rank
        for name, rank in _IMPACT_RANK.items():
            if rank == target_rank:
                return name

    return current_impact
