"""TfL Live Traffic Disruptions poller.

Polls the TfL Unified API for road disruptions every 5 minutes,
geo-filters to target boroughs, classifies cycling impact, and
upserts to a Notion Disruptions database.
"""

from __future__ import annotations

import logging

import httpx
from shapely.geometry import Point, shape

from src.config import settings

logger = logging.getLogger(__name__)

TFL_DISRUPTIONS_URL = "https://api.tfl.gov.uk/Road/all/Disruption"


async def fetch_disruptions() -> list[dict]:
    """Fetch current disruptions from the TfL API."""
    params = {}
    if settings.tfl_api_key:
        params["app_key"] = settings.tfl_api_key

    async with httpx.AsyncClient() as client:
        resp = await client.get(TFL_DISRUPTIONS_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()


def extract_point(disruption: dict) -> Point | None:
    """Extract a WGS84 point from a TfL disruption's geography field.

    The geography field can be a GeoJSON geometry (Point or LineString).
    For LineStrings, we use the centroid.
    """
    geo = disruption.get("geography")
    if not geo:
        return None

    try:
        geom = shape(geo)
        if geom.is_empty:
            return None
        # Use centroid for any geometry type
        return geom.centroid
    except Exception:
        logger.debug("Could not parse disruption geography: %s", disruption.get("id"))
        return None


def classify_disruption_impact(disruption: dict) -> str:
    """Classify cycling impact of a TfL disruption.

    Returns one of: "high", "medium", "low", "minimal".

    TfL API categories (observed): Collisions, Hazards, Works,
    Network delays, Asset issues, Breakdowns, Planned events.
    Severities: Serious, Moderate, Minimal.
    """
    category = (disruption.get("category") or "").lower()
    severity = (disruption.get("severity") or "").lower()

    # Serious severity is always high impact
    if severity == "serious":
        return "high"

    # Collisions and hazards are high impact for cyclists
    if category in ("collisions", "hazards"):
        return "high"

    # Moderate severity or events/breakdowns that disrupt traffic
    if severity == "moderate":
        return "medium"
    if category in ("planned events", "breakdowns", "network delays", "asset issues"):
        return "medium"

    # Works with minimal severity
    if category == "works" and severity == "minimal":
        return "low"

    return "low"
