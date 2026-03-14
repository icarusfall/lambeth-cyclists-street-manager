"""Download and pre-filter TfL Cycling Infrastructure Database (CID) data.

Usage:
    python -m scripts.download_cid

Downloads three datasets:
  1. CID cycle lanes/tracks — filtered to target boroughs
  2. CID restricted routes (modal filters) — filtered to target boroughs
  3. TfL Cycleway routes — all routes (small dataset, 146 features)

Saves pre-filtered GeoJSON files to data/ for use at runtime.
"""

import json
import logging
import sys
from pathlib import Path
from urllib.request import urlopen

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

CID_CYCLE_LANES_URL = (
    "https://cycling.data.tfl.gov.uk/CyclingInfrastructure/data/lines/cycle_lane_track.json"
)
CID_RESTRICTED_ROUTES_URL = (
    "https://cycling.data.tfl.gov.uk/CyclingInfrastructure/data/lines/restricted_route.json"
)
CYCLE_ROUTES_URL = (
    "https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/"
    "Cycle_Routes/FeatureServer/11/query"
    "?where=1%3D1&outFields=*&f=geojson&resultRecordCount=2000"
)


def _download_json(url: str) -> dict:
    """Download and parse a JSON file from a URL."""
    logger.info("Downloading %s", url[:100])
    with urlopen(url) as resp:
        return json.loads(resp.read())


def _filter_by_borough(geojson: dict, target_boroughs: set[str]) -> dict:
    """Filter a GeoJSON FeatureCollection to features in target boroughs."""
    original_count = len(geojson["features"])
    filtered = [
        f for f in geojson["features"]
        if f.get("properties", {}).get("BOROUGH", "") in target_boroughs
    ]
    logger.info(
        "Filtered %d → %d features (target boroughs: %s)",
        original_count, len(filtered), ", ".join(sorted(target_boroughs)),
    )
    return {
        "type": "FeatureCollection",
        "features": filtered,
    }


def main() -> None:
    target_boroughs = set(settings.get_target_boroughs())
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. CID cycle lanes/tracks
    logger.info("=== Downloading CID cycle lanes/tracks ===")
    cycle_lanes = _download_json(CID_CYCLE_LANES_URL)
    cycle_lanes_filtered = _filter_by_borough(cycle_lanes, target_boroughs)
    out_path = DATA_DIR / "cid_cycle_lanes.json"
    out_path.write_text(json.dumps(cycle_lanes_filtered), encoding="utf-8")
    logger.info("Saved %s (%d features)", out_path, len(cycle_lanes_filtered["features"]))

    # 2. CID restricted routes (modal filters, traffic gates)
    logger.info("=== Downloading CID restricted routes ===")
    restricted = _download_json(CID_RESTRICTED_ROUTES_URL)
    restricted_filtered = _filter_by_borough(restricted, target_boroughs)
    out_path = DATA_DIR / "cid_restricted_routes.json"
    out_path.write_text(json.dumps(restricted_filtered), encoding="utf-8")
    logger.info("Saved %s (%d features)", out_path, len(restricted_filtered["features"]))

    # 3. TfL Cycleway routes (small dataset — download all)
    logger.info("=== Downloading TfL Cycleway routes ===")
    cycle_routes = _download_json(CYCLE_ROUTES_URL)
    out_path = DATA_DIR / "cycle_routes.json"
    out_path.write_text(json.dumps(cycle_routes), encoding="utf-8")
    logger.info("Saved %s (%d features)", out_path, len(cycle_routes.get("features", [])))

    logger.info("=== Done ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
