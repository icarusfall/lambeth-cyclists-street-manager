"""Load London borough boundary polygons from a GeoJSON file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)

# Property keys that different GeoJSON sources use for borough names.
_NAME_KEYS = ["NAME", "name", "LAD24NM", "LAD23NM", "LAD22NM", "lad_name"]


def _get_feature_name(properties: dict) -> str | None:
    """Extract borough name from GeoJSON feature properties."""
    for key in _NAME_KEYS:
        if key in properties:
            return properties[key]
    return None


def load_borough_polygons(
    geojson_path: str | Path,
    target_boroughs: list[str],
) -> dict[str, BaseGeometry]:
    """Load and return polygons for the target boroughs.

    Args:
        geojson_path: Path to a London boroughs GeoJSON file.
        target_boroughs: Borough names to extract.

    Returns:
        Dict mapping borough name to its Shapely polygon/multipolygon.

    Raises:
        FileNotFoundError: If the GeoJSON file doesn't exist.
        ValueError: If any target borough isn't found in the file.
    """
    path = Path(geojson_path)
    if not path.exists():
        raise FileNotFoundError(f"Borough boundary file not found: {path}")

    with open(path) as f:
        data = json.load(f)

    # Normalise target names for case-insensitive matching
    target_lookup = {name.lower(): name for name in target_boroughs}
    polygons: dict[str, BaseGeometry] = {}

    for feature in data["features"]:
        name = _get_feature_name(feature["properties"])
        if name and name.lower() in target_lookup:
            canonical_name = target_lookup[name.lower()]
            polygons[canonical_name] = shape(feature["geometry"])
            logger.info("Loaded boundary for %s", canonical_name)

    missing = set(target_boroughs) - set(polygons.keys())
    if missing:
        # Log available names to help debug property key issues
        available = [_get_feature_name(f["properties"]) for f in data["features"]]
        available = [n for n in available if n]
        logger.error("Available borough names in GeoJSON: %s", sorted(available))
        raise ValueError(f"Boroughs not found in GeoJSON: {missing}")

    logger.info("Loaded %d borough boundaries", len(polygons))
    return polygons
