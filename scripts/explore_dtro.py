"""Explore the D-TRO API to assess data availability for target boroughs.

Usage:
    python -m scripts.explore_dtro

Authenticates with the D-TRO production API, searches for D-TROs published
by our target borough traffic authorities, and reports what's available.

Requires env vars: DTRO_APP_ID, DTRO_API_KEY, DTRO_API_SECRET
"""

import logging
import sys
from pathlib import Path

import httpx

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings

logger = logging.getLogger(__name__)

DTRO_BASE_URL = "https://dtro.dft.gov.uk/v1"

# Traffic authority SWA codes for our target boroughs.
# The D-TRO API uses traCreator/currentTraOwner as integer filters.
# These are the same SWA codes used in config.py.
BOROUGH_TRA_CODES: dict[int, str] = {
    5660: "Lambeth",
    5840: "Southwark",
    5960: "Wandsworth",
    5690: "Lewisham",
    5720: "Merton",
    5240: "Croydon",
    5030: "City of London",
    5990: "Westminster",
    20: "Transport for London",
}


def get_dtro_settings() -> tuple[str, str, str]:
    """Read D-TRO credentials from environment."""
    app_id = getattr(settings, "dtro_app_id", "") or ""
    api_key = getattr(settings, "dtro_api_key", "") or ""
    api_secret = getattr(settings, "dtro_api_secret", "") or ""
    return app_id, api_key, api_secret


def get_access_token(
    client: httpx.Client, app_id: str, api_key: str, api_secret: str,
) -> str:
    """Exchange client credentials for an OAuth2 bearer token.

    Auth uses API Key as client_id and API Secret as client_secret.
    """
    resp = client.post(
        f"{DTRO_BASE_URL}/oauth-generator",
        auth=(api_key, api_secret),
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    logger.info("Got access token (expires in 30 min)")
    return token


def search_by_tra(client: httpx.Client, token: str, tra_code: int) -> dict:
    """Search for D-TROs created by a specific traffic authority."""
    resp = client.post(
        f"{DTRO_BASE_URL}/search",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "page": 1,
            "pageSize": 10,
            "queries": [{"traCreator": tra_code}],
        },
    )
    resp.raise_for_status()
    return resp.json()


def search_all(client: httpx.Client, token: str) -> dict:
    """Search for all D-TROs (no filter, first page)."""
    resp = client.post(
        f"{DTRO_BASE_URL}/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"page": 1, "pageSize": 10, "queries": [{}]},
    )
    resp.raise_for_status()
    return resp.json()


def get_dtro_by_id(client: httpx.Client, token: str, dtro_id: str) -> dict:
    """Fetch a single D-TRO by ID for inspection."""
    resp = client.get(
        f"{DTRO_BASE_URL}/dtros/{dtro_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    app_id, api_key, api_secret = get_dtro_settings()

    if not api_key or not api_secret:
        logger.error(
            "DTRO_API_KEY and DTRO_API_SECRET must be set. "
            "Add them to .env or set as environment variables."
        )
        sys.exit(1)

    with httpx.Client(timeout=30) as client:
        # Step 1: Authenticate
        print("=" * 60)
        print("D-TRO API Explorer")
        print("=" * 60)

        try:
            token = get_access_token(client, app_id, api_key, api_secret)
        except httpx.HTTPStatusError as e:
            logger.error("Authentication failed: %s %s", e.response.status_code, e.response.text)
            sys.exit(1)

        # Step 2: Search for all D-TROs to get a sense of total volume
        print("\n--- Overall D-TRO volume ---")
        try:
            all_results = search_all(client, token)
            print(f"Response keys: {list(all_results.keys())}")
            total = all_results.get("totalCount", all_results.get("total", "unknown"))
            page_results = all_results.get("dtros", all_results.get("results", []))
            print(f"Total D-TROs in system: {total}")
            print(f"Results on page 1: {len(page_results)}")

            # Show a sample record structure
            if page_results:
                sample = page_results[0]
                print(f"\nSample D-TRO keys: {list(sample.keys())}")
                # Print key fields if they exist
                for key in ["id", "traCreator", "currentTraOwner", "troName",
                            "regulationType", "publicationTime", "modificationTime"]:
                    if key in sample:
                        print(f"  {key}: {sample[key]}")
        except httpx.HTTPStatusError as e:
            print(f"Search failed: {e.response.status_code} {e.response.text}")

        # Step 3: Search by each target borough
        print("\n--- D-TROs by target borough ---")
        boroughs_with_data = []

        for tra_code, borough_name in BOROUGH_TRA_CODES.items():
            try:
                results = search_by_tra(client, token, tra_code)
                total = results.get("totalCount", results.get("total", 0))
                page_results = results.get("dtros", results.get("results", []))

                status = f"{total} D-TROs" if total else "No data"
                print(f"  {borough_name} (SWA {tra_code}): {status}")

                if total and total > 0:
                    boroughs_with_data.append((borough_name, tra_code, total))

                    # Show a sample from this borough
                    if page_results:
                        sample = page_results[0]
                        tro_name = sample.get("troName", "unnamed")
                        reg_type = sample.get("regulationType", "unknown")
                        print(f"    Sample: {tro_name} ({reg_type})")

            except httpx.HTTPStatusError as e:
                print(f"  {borough_name} (SWA {tra_code}): Error {e.response.status_code}")

        # Step 4: If we found data, fetch a full D-TRO to see the complete structure
        print("\n--- Full D-TRO inspection ---")
        if boroughs_with_data:
            borough_name, tra_code, _ = boroughs_with_data[0]
            try:
                results = search_by_tra(client, token, tra_code)
                page_results = results.get("dtros", results.get("results", []))
                if page_results:
                    dtro_id = page_results[0].get("id")
                    if dtro_id:
                        full_dtro = get_dtro_by_id(client, token, dtro_id)
                        print(f"Full D-TRO from {borough_name} (ID: {dtro_id}):")
                        _print_nested(full_dtro, indent=2, max_depth=5)
            except httpx.HTTPStatusError as e:
                print(f"Fetch failed: {e.response.status_code} {e.response.text}")
        else:
            # Try fetching the first result from the general search
            try:
                all_results = search_all(client, token)
                page_results = all_results.get("dtros", all_results.get("results", []))
                if page_results:
                    dtro_id = page_results[0].get("id")
                    if dtro_id:
                        full_dtro = get_dtro_by_id(client, token, dtro_id)
                        print(f"Sample D-TRO (ID: {dtro_id}):")
                        _print_nested(full_dtro, indent=2, max_depth=3)
                else:
                    print("No D-TROs found in the system at all.")
            except httpx.HTTPStatusError as e:
                print(f"Fetch failed: {e.response.status_code} {e.response.text}")

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        if boroughs_with_data:
            print(f"\n{len(boroughs_with_data)} target borough(s) have D-TRO data:")
            for name, code, count in boroughs_with_data:
                print(f"  - {name}: {count} D-TROs")
            print("\nRecommendation: Proceed with Phase 4 integration.")
        else:
            print("\nNo target boroughs are publishing D-TROs yet.")
            print("Recommendation: Defer Phase 4 — check again in a few months.")


def _print_nested(obj, indent: int = 0, max_depth: int = 3, _depth: int = 0) -> None:
    """Pretty-print a nested dict/list, truncating at max_depth."""
    prefix = " " * indent
    if _depth >= max_depth:
        print(f"{prefix}... (truncated)")
        return

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                print(f"{prefix}{key}:")
                _print_nested(value, indent + 2, max_depth, _depth + 1)
            else:
                val_str = str(value)
                if len(val_str) > 120:
                    val_str = val_str[:120] + "..."
                print(f"{prefix}{key}: {val_str}")
    elif isinstance(obj, list):
        print(f"{prefix}[{len(obj)} items]")
        for item in obj[:3]:  # Show first 3
            _print_nested(item, indent + 2, max_depth, _depth + 1)
        if len(obj) > 3:
            print(f"{prefix}  ... and {len(obj) - 3} more")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
