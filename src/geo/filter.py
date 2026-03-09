"""Two-tier geo-filter: SWA code fast path + BNG-to-WGS84 point-in-polygon."""

from __future__ import annotations

import logging
import re

from pyproj import Transformer
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from src.config import BOROUGH_SWA_CODES

logger = logging.getLogger(__name__)

# Module-level transformer — thread-safe, reusable.
_transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

# Regex for Street Manager WKT coordinates: POINT(easting northing)
_BNG_WKT_PATTERN = re.compile(r"POINT\(([\d.]+)\s+([\d.]+)\)")


def parse_bng_wkt_to_wgs84(wkt: str) -> Point | None:
    """Convert a BNG WKT POINT string to a WGS84 Shapely Point.

    Args:
        wkt: e.g. "POINT(527155.33 182227.95)"

    Returns:
        Shapely Point(lon, lat) in WGS84, or None if parsing fails.
    """
    match = _BNG_WKT_PATTERN.match(wkt)
    if not match:
        logger.warning("Could not parse BNG WKT: %s", wkt)
        return None

    easting, northing = float(match.group(1)), float(match.group(2))
    lon, lat = _transformer.transform(easting, northing)
    return Point(lon, lat)


class GeoFilter:
    """Determines whether a Street Manager work falls within target boroughs."""

    def __init__(self, borough_polygons: dict[str, BaseGeometry]) -> None:
        self._polygons = borough_polygons
        self._swa_to_borough = dict(BOROUGH_SWA_CODES)

    def check(self, object_data: dict) -> tuple[bool, str]:
        """Check whether a work notification is in our target area.

        Args:
            object_data: The object_data dict from an SNS notification.

        Returns:
            (should_include, borough_name). borough_name is empty if excluded.
        """
        ha_swa = object_data.get("highway_authority_swa_code", "")

        # Fast path: highway authority IS one of our target boroughs
        if ha_swa in self._swa_to_borough:
            return True, self._swa_to_borough[ha_swa]

        # Geo path: for TfL roads, cross-boundary works, etc.
        coords_wkt = object_data.get("works_location_coordinates")
        if not coords_wkt:
            return False, ""

        point = parse_bng_wkt_to_wgs84(coords_wkt)
        if point is None:
            return False, ""

        for borough_name, polygon in self._polygons.items():
            if polygon.contains(point):
                return True, borough_name

        return False, ""

    def check_wgs84_point(self, point: Point) -> tuple[bool, str]:
        """Check whether a WGS84 point falls within a target borough.

        Args:
            point: Shapely Point(lon, lat) in WGS84.

        Returns:
            (should_include, borough_name). borough_name is empty if excluded.
        """
        for borough_name, polygon in self._polygons.items():
            if polygon.contains(point):
                return True, borough_name
        return False, ""
