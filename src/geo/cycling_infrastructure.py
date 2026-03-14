"""Cycling infrastructure spatial index for proximity-based impact scoring.

Loads pre-filtered CID data (cycle lanes/tracks, restricted routes) and TfL
Cycleway routes, builds a Shapely STRtree for fast proximity queries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

# Approximate metres per degree at London's latitude (~51.5°N)
_M_PER_DEG_LAT = 111_320
_M_PER_DEG_LON = 111_320 * 0.6252  # cos(51.5°)


def _metres_to_degrees(metres: float) -> float:
    """Convert metres to approximate degrees (conservative, uses smaller axis)."""
    return metres / _M_PER_DEG_LON


@dataclass
class CIDResult:
    """Result of a cycling infrastructure proximity check."""

    asset_type: str  # e.g. "segregated_cycleway", "modal_filter", "cycleway_route"
    description: str  # Human-readable, e.g. "Cycleway 7 — segregated cycle track"
    distance_m: float  # Approximate distance in metres
    route_name: str | None  # Named route if applicable, e.g. "Cycleway 7"

    def format_notion(self) -> str:
        """Format for the Notion 'Nearby Cycling Infrastructure' field."""
        dist = f"{self.distance_m:.0f}m"
        if self.route_name:
            return f"{self.route_name} — {self.description} ({dist})"
        return f"{self.description} ({dist})"


# Priority order for asset types (lower = higher priority)
_ASSET_PRIORITY = {
    "cycleway_route": 0,
    "segregated_cycleway": 1,
    "stepped_cycleway": 2,
    "partially_segregated_cycleway": 3,
    "mandatory_lane": 4,
    "modal_filter": 5,
    "contraflow_lane": 6,
    "advisory_lane": 7,
    "shared_use_path": 8,
}


def _classify_cycle_lane(properties: dict) -> tuple[str, str]:
    """Classify a CID cycle lane/track feature into asset type and description."""
    if properties.get("CLT_SEGREG") == "TRUE":
        return "segregated_cycleway", "Segregated cycle track"
    if properties.get("CLT_STEPP") == "TRUE":
        return "stepped_cycleway", "Stepped cycle track"
    if properties.get("CLT_PARSEG") == "TRUE":
        return "partially_segregated_cycleway", "Partially segregated cycle track"
    if properties.get("CLT_MANDAT") == "TRUE":
        return "mandatory_lane", "Mandatory cycle lane"
    if properties.get("CLT_CONTRA") == "TRUE":
        return "contraflow_lane", "Contraflow cycle lane"
    if properties.get("CLT_ADVIS") == "TRUE":
        return "advisory_lane", "Advisory cycle lane"
    if properties.get("CLT_SHARED") == "TRUE":
        return "shared_use_path", "Shared use path"
    return "advisory_lane", "Cycle lane"


def _geojson_to_shapely(feature: dict) -> LineString | MultiLineString | None:
    """Convert a GeoJSON feature geometry to a Shapely geometry."""
    geom = feature.get("geometry")
    if not geom:
        return None
    try:
        return shape(geom)
    except Exception:
        return None


def _degrees_to_metres(degrees: float) -> float:
    """Convert degrees to approximate metres at London's latitude."""
    return degrees * _M_PER_DEG_LON


class CyclingInfrastructureIndex:
    """Spatial index of cycling infrastructure for proximity queries."""

    def __init__(
        self,
        geometries: list[LineString | MultiLineString],
        metadata: list[dict],
    ) -> None:
        """Build the spatial index.

        Args:
            geometries: List of Shapely geometries (one per feature).
            metadata: List of dicts with keys: asset_type, description, route_name.
                      Must be same length as geometries.
        """
        self._geometries = geometries
        self._metadata = metadata
        self._tree = STRtree(geometries) if geometries else None
        logger.info("Built CID spatial index with %d features", len(geometries))

    @property
    def feature_count(self) -> int:
        return len(self._geometries)

    def check_proximity(self, point: Point, radius_m: float = 50.0) -> CIDResult | None:
        """Find the most important cycling infrastructure near a point.

        Args:
            point: WGS84 Point(lon, lat).
            radius_m: Search radius in metres.

        Returns:
            CIDResult for the highest-priority nearby infrastructure, or None.
        """
        if not self._tree:
            return None

        # Buffer the point by the search radius (converted to degrees)
        buffer_deg = _metres_to_degrees(radius_m)
        search_area = point.buffer(buffer_deg)

        # Query the STRtree for candidate geometries
        candidate_indices = self._tree.query(search_area)
        if len(candidate_indices) == 0:
            return None

        # Find all features within the actual radius
        matches: list[tuple[float, dict]] = []
        for idx in candidate_indices:
            geom = self._geometries[idx]
            dist_deg = point.distance(geom)
            dist_m = _degrees_to_metres(dist_deg)
            if dist_m <= radius_m:
                matches.append((dist_m, self._metadata[idx]))

        if not matches:
            return None

        # Sort by priority (asset type), then by distance
        matches.sort(key=lambda m: (_ASSET_PRIORITY.get(m[1]["asset_type"], 99), m[0]))

        best_dist, best_meta = matches[0]
        return CIDResult(
            asset_type=best_meta["asset_type"],
            description=best_meta["description"],
            distance_m=round(best_dist, 1),
            route_name=best_meta.get("route_name"),
        )

    @classmethod
    def load(cls, data_dir: str | Path) -> CyclingInfrastructureIndex:
        """Load CID data from pre-filtered JSON files in data_dir.

        Expects:
          - data_dir/cid_cycle_lanes.json
          - data_dir/cid_restricted_routes.json
          - data_dir/cycle_routes.json (optional)

        Returns a CyclingInfrastructureIndex, possibly empty if files are missing.
        """
        data_dir = Path(data_dir)
        geometries: list[LineString | MultiLineString] = []
        metadata: list[dict] = []

        # 1. Cycle lanes/tracks
        cycle_lanes_path = data_dir / "cid_cycle_lanes.json"
        if cycle_lanes_path.exists():
            with open(cycle_lanes_path, encoding="utf-8") as f:
                data = json.load(f)
            for feature in data.get("features", []):
                geom = _geojson_to_shapely(feature)
                if geom is None:
                    continue
                asset_type, description = _classify_cycle_lane(
                    feature.get("properties", {})
                )
                geometries.append(geom)
                metadata.append({
                    "asset_type": asset_type,
                    "description": description,
                    "route_name": None,
                })
            logger.info("Loaded %d cycle lane features", len(data.get("features", [])))
        else:
            logger.warning("CID cycle lanes file not found: %s", cycle_lanes_path)

        # 2. Restricted routes (modal filters)
        restricted_path = data_dir / "cid_restricted_routes.json"
        if restricted_path.exists():
            with open(restricted_path, encoding="utf-8") as f:
                data = json.load(f)
            for feature in data.get("features", []):
                geom = _geojson_to_shapely(feature)
                if geom is None:
                    continue
                geometries.append(geom)
                metadata.append({
                    "asset_type": "modal_filter",
                    "description": "Modal filter / restricted route",
                    "route_name": None,
                })
            logger.info("Loaded %d restricted route features", len(data.get("features", [])))
        else:
            logger.warning("CID restricted routes file not found: %s", restricted_path)

        # 3. Cycleway routes (optional)
        routes_path = data_dir / "cycle_routes.json"
        if routes_path.exists():
            with open(routes_path, encoding="utf-8") as f:
                data = json.load(f)
            for feature in data.get("features", []):
                geom = _geojson_to_shapely(feature)
                if geom is None:
                    continue
                props = feature.get("properties", {})
                route_name = props.get("Route_Name", "")
                status = props.get("Status", "")
                # Only include open routes
                if status and status != "Open":
                    continue
                geometries.append(geom)
                metadata.append({
                    "asset_type": "cycleway_route",
                    "description": route_name or "Cycleway route",
                    "route_name": route_name or None,
                })
            logger.info("Loaded %d Cycleway route features", len(data.get("features", [])))
        else:
            logger.info("Cycleway routes file not found (optional): %s", routes_path)

        return cls(geometries, metadata)
