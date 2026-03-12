"""D-TRO API client — OAuth2 auth, search, and fetch.

Production API at https://dtro.dft.gov.uk/v1.
Auth: OAuth2 client credentials (API Key + API Secret → bearer token, 30 min TTL).
"""

from __future__ import annotations

import logging
import time

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

DTRO_BASE_URL = "https://dtro.dft.gov.uk/v1"


class DtroClient:
    """Client for the D-TRO production API."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0

    async def _ensure_token(self, client: httpx.AsyncClient) -> str:
        """Get a valid bearer token, refreshing if expired."""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        resp = await client.post(
            f"{DTRO_BASE_URL}/oauth-generator",
            auth=(settings.dtro_api_key, settings.dtro_api_secret),
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        # Refresh 2 minutes before expiry (tokens last 30 min)
        self._token_expires_at = time.time() + 28 * 60
        logger.info("D-TRO: obtained access token")
        return self._token

    async def search_by_tra(
        self,
        tra_code: int,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Search for D-TROs created by a specific traffic authority."""
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._ensure_token(client)
            resp = await client.post(
                f"{DTRO_BASE_URL}/search",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "page": page,
                    "pageSize": page_size,
                    "queries": [{"traCreator": tra_code}],
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def search_all_boroughs(self, page_size: int = 50) -> list[dict]:
        """Search for D-TROs from all target borough traffic authorities.

        Returns combined search result items from all boroughs.
        """
        from src.config import BOROUGH_SWA_CODES

        all_results: list[dict] = []

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._ensure_token(client)

            for swa_code in BOROUGH_SWA_CODES:
                tra_code = int(swa_code)
                page = 1
                try:
                    while True:
                        resp = await client.post(
                            f"{DTRO_BASE_URL}/search",
                            headers={"Authorization": f"Bearer {token}"},
                            json={
                                "page": page,
                                "pageSize": page_size,
                                "queries": [{"traCreator": tra_code}],
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        results = data.get("results", [])
                        all_results.extend(results)

                        total_pages = data.get("totalPages", 1)
                        if page >= total_pages:
                            break
                        page += 1
                except httpx.HTTPStatusError as e:
                    # Some boroughs have no D-TROs — the API returns 400
                    logger.debug(
                        "D-TRO search for SWA %d returned %d — skipping",
                        tra_code, e.response.status_code,
                    )

        # Also try TfL (SWA 20)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self._ensure_token(client)
                resp = await client.post(
                    f"{DTRO_BASE_URL}/search",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "page": 1,
                        "pageSize": page_size,
                        "queries": [{"traCreator": 20}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                all_results.extend(data.get("results", []))
        except httpx.HTTPStatusError:
            logger.debug("D-TRO search for TfL (SWA 20) failed — skipping")

        return all_results

    async def get_dtro(self, dtro_id: str) -> dict:
        """Fetch a single D-TRO by ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._ensure_token(client)
            resp = await client.get(
                f"{DTRO_BASE_URL}/dtros/{dtro_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_events(
        self,
        since: str | None = None,
        tra_code: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Fetch D-TRO events (changes) with optional filters.

        Args:
            since: ISO datetime string — only return events after this time.
            tra_code: Filter by traffic authority creator SWA code.
            page: Page number (1-based).
            page_size: Results per page.
        """
        body: dict = {"page": page, "pageSize": page_size}
        if since:
            body["since"] = since
        if tra_code:
            body["traCreator"] = tra_code

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._ensure_token(client)
            resp = await client.post(
                f"{DTRO_BASE_URL}/events",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
