"""London Air Quality Network (LAQN) API client.

Public API at https://api.erg.ic.ac.uk/AirQuality — no auth required.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

LAQN_BASE_URL = "https://api.erg.ic.ac.uk/AirQuality"

# LAQN LocalAuthorityId for each target borough
BOROUGH_LA_IDS: dict[int, str] = {
    22: "Lambeth",
    28: "Southwark",
    32: "Wandsworth",
    23: "Lewisham",
    24: "Merton",
    8: "Croydon",
    7: "City of London",
    33: "Westminster",
}


async def fetch_daily_index_for_borough(la_id: int) -> dict:
    """Fetch the latest daily air quality index for a local authority."""
    url = f"{LAQN_BASE_URL}/Daily/MonitoringIndex/Latest/LocalAuthorityId={la_id}/Json"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
