"""Tests for the cycling infrastructure spatial index and CID impact upgrade."""

import json
import tempfile
from pathlib import Path

from shapely.geometry import LineString, Point

from src.classifier.rules import upgrade_impact_with_cid
from src.geo.cycling_infrastructure import (
    CIDResult,
    CyclingInfrastructureIndex,
    _classify_cycle_lane,
)


# --- Helpers ---

def _make_linestring_feature(coords, properties=None):
    """Create a GeoJSON feature with a LineString geometry."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
        "properties": properties or {},
    }


def _make_geojson(features):
    return {"type": "FeatureCollection", "features": features}


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


# --- Test CIDResult ---

class TestCIDResult:
    def test_format_notion_with_route_name(self):
        r = CIDResult("cycleway_route", "Cycleway 7", 12.3, "Cycleway 7")
        assert r.format_notion() == "Cycleway 7 — Cycleway 7 (12m)"

    def test_format_notion_without_route_name(self):
        r = CIDResult("segregated_cycleway", "Segregated cycle track", 34.0, None)
        assert r.format_notion() == "Segregated cycle track (34m)"

    def test_format_notion_zero_distance(self):
        r = CIDResult("modal_filter", "Modal filter / restricted route", 0.0, None)
        assert r.format_notion() == "Modal filter / restricted route (0m)"


# --- Test _classify_cycle_lane ---

class TestClassifyCycleLane:
    def test_segregated(self):
        assert _classify_cycle_lane({"CLT_SEGREG": "TRUE"}) == (
            "segregated_cycleway", "Segregated cycle track"
        )

    def test_stepped(self):
        assert _classify_cycle_lane({"CLT_STEPP": "TRUE"}) == (
            "stepped_cycleway", "Stepped cycle track"
        )

    def test_partially_segregated(self):
        assert _classify_cycle_lane({"CLT_PARSEG": "TRUE"}) == (
            "partially_segregated_cycleway", "Partially segregated cycle track"
        )

    def test_mandatory(self):
        assert _classify_cycle_lane({"CLT_MANDAT": "TRUE"}) == (
            "mandatory_lane", "Mandatory cycle lane"
        )

    def test_contraflow(self):
        assert _classify_cycle_lane({"CLT_CONTRA": "TRUE"}) == (
            "contraflow_lane", "Contraflow cycle lane"
        )

    def test_advisory(self):
        assert _classify_cycle_lane({"CLT_ADVIS": "TRUE"}) == (
            "advisory_lane", "Advisory cycle lane"
        )

    def test_shared(self):
        assert _classify_cycle_lane({"CLT_SHARED": "TRUE"}) == (
            "shared_use_path", "Shared use path"
        )

    def test_unknown_defaults_to_advisory(self):
        assert _classify_cycle_lane({}) == ("advisory_lane", "Cycle lane")

    def test_priority_segregated_over_advisory(self):
        # If both TRUE, segregated should win (checked first)
        assert _classify_cycle_lane({"CLT_SEGREG": "TRUE", "CLT_ADVIS": "TRUE"})[0] == (
            "segregated_cycleway"
        )


# --- Test CyclingInfrastructureIndex ---

class TestCyclingInfrastructureIndex:
    def _build_index(self, features_with_meta):
        """Build an index from (geometry, metadata) tuples."""
        geoms = [f[0] for f in features_with_meta]
        meta = [f[1] for f in features_with_meta]
        return CyclingInfrastructureIndex(geoms, meta)

    def test_empty_index_returns_none(self):
        idx = CyclingInfrastructureIndex([], [])
        assert idx.check_proximity(Point(-0.1, 51.5)) is None
        assert idx.feature_count == 0

    def test_finds_nearby_feature(self):
        # A cycle lane near (-0.1, 51.5)
        line = LineString([(-0.1001, 51.5), (-0.0999, 51.5)])
        idx = self._build_index([
            (line, {"asset_type": "segregated_cycleway", "description": "Segregated cycle track", "route_name": None})
        ])
        result = idx.check_proximity(Point(-0.1, 51.5001), radius_m=50)
        assert result is not None
        assert result.asset_type == "segregated_cycleway"
        assert result.distance_m < 50

    def test_returns_none_when_nothing_nearby(self):
        # A cycle lane far from the query point
        line = LineString([(-0.2, 51.6), (-0.2, 51.601)])
        idx = self._build_index([
            (line, {"asset_type": "segregated_cycleway", "description": "Segregated cycle track", "route_name": None})
        ])
        result = idx.check_proximity(Point(-0.1, 51.5), radius_m=50)
        assert result is None

    def test_priority_ordering_cycleway_route_over_advisory(self):
        # Two features at similar distance — cycleway route should win
        line1 = LineString([(-0.1001, 51.5), (-0.0999, 51.5)])
        line2 = LineString([(-0.1002, 51.5), (-0.0998, 51.5)])
        idx = self._build_index([
            (line1, {"asset_type": "advisory_lane", "description": "Advisory cycle lane", "route_name": None}),
            (line2, {"asset_type": "cycleway_route", "description": "Cycleway 7", "route_name": "Cycleway 7"}),
        ])
        result = idx.check_proximity(Point(-0.1, 51.5001), radius_m=50)
        assert result is not None
        assert result.asset_type == "cycleway_route"
        assert result.route_name == "Cycleway 7"

    def test_priority_ordering_segregated_over_modal_filter(self):
        line1 = LineString([(-0.1001, 51.5), (-0.0999, 51.5)])
        line2 = LineString([(-0.1002, 51.5), (-0.0998, 51.5)])
        idx = self._build_index([
            (line1, {"asset_type": "modal_filter", "description": "Modal filter", "route_name": None}),
            (line2, {"asset_type": "segregated_cycleway", "description": "Segregated cycle track", "route_name": None}),
        ])
        result = idx.check_proximity(Point(-0.1, 51.5001), radius_m=50)
        assert result is not None
        assert result.asset_type == "segregated_cycleway"

    def test_feature_count(self):
        line = LineString([(-0.1, 51.5), (-0.1, 51.501)])
        idx = self._build_index([
            (line, {"asset_type": "segregated_cycleway", "description": "test", "route_name": None}),
        ])
        assert idx.feature_count == 1


# --- Test CyclingInfrastructureIndex.load ---

class TestCIDLoad:
    def test_load_from_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Write cycle lanes
            _write_json(data_dir / "cid_cycle_lanes.json", _make_geojson([
                _make_linestring_feature(
                    [[-0.1, 51.5], [-0.1, 51.501]],
                    {"CLT_SEGREG": "TRUE", "BOROUGH": "Lambeth"},
                ),
            ]))

            # Write restricted routes
            _write_json(data_dir / "cid_restricted_routes.json", _make_geojson([
                _make_linestring_feature(
                    [[-0.11, 51.5], [-0.11, 51.501]],
                    {"BOROUGH": "Lambeth"},
                ),
            ]))

            # Write cycle routes
            _write_json(data_dir / "cycle_routes.json", _make_geojson([
                _make_linestring_feature(
                    [[-0.12, 51.5], [-0.12, 51.501]],
                    {"Route_Name": "Cycleway 5", "Label": "C5", "Status": "Open"},
                ),
            ]))

            idx = CyclingInfrastructureIndex.load(data_dir)
            assert idx.feature_count == 3

    def test_load_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = CyclingInfrastructureIndex.load(tmpdir)
            assert idx.feature_count == 0

    def test_load_skips_non_open_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_json(data_dir / "cycle_routes.json", _make_geojson([
                _make_linestring_feature(
                    [[-0.12, 51.5], [-0.12, 51.501]],
                    {"Route_Name": "Cycleway 99", "Status": "Proposed"},
                ),
                _make_linestring_feature(
                    [[-0.13, 51.5], [-0.13, 51.501]],
                    {"Route_Name": "Cycleway 5", "Status": "Open"},
                ),
            ]))
            idx = CyclingInfrastructureIndex.load(data_dir)
            assert idx.feature_count == 1


# --- Test upgrade_impact_with_cid ---

class TestUpgradeImpactWithCid:
    def test_none_result_no_change(self):
        assert upgrade_impact_with_cid("low", None) == "low"
        assert upgrade_impact_with_cid("high", None) == "high"

    def test_segregated_upgrades_low_to_high(self):
        result = CIDResult("segregated_cycleway", "Segregated cycle track", 10.0, None)
        assert upgrade_impact_with_cid("low", result) == "high"

    def test_segregated_upgrades_minimal_to_high(self):
        result = CIDResult("segregated_cycleway", "Segregated cycle track", 10.0, None)
        assert upgrade_impact_with_cid("minimal", result) == "high"

    def test_segregated_keeps_high_as_high(self):
        result = CIDResult("segregated_cycleway", "Segregated cycle track", 10.0, None)
        assert upgrade_impact_with_cid("high", result) == "high"

    def test_cycleway_route_upgrades_low_to_high(self):
        result = CIDResult("cycleway_route", "Cycleway 7", 5.0, "Cycleway 7")
        assert upgrade_impact_with_cid("low", result) == "high"

    def test_modal_filter_upgrades_low_to_medium(self):
        result = CIDResult("modal_filter", "Modal filter", 10.0, None)
        assert upgrade_impact_with_cid("low", result) == "medium"

    def test_modal_filter_upgrades_minimal_to_medium(self):
        result = CIDResult("modal_filter", "Modal filter", 10.0, None)
        assert upgrade_impact_with_cid("minimal", result) == "medium"

    def test_modal_filter_does_not_downgrade_high(self):
        result = CIDResult("modal_filter", "Modal filter", 10.0, None)
        assert upgrade_impact_with_cid("high", result) == "high"

    def test_advisory_lane_upgrades_low_to_medium(self):
        result = CIDResult("advisory_lane", "Advisory cycle lane", 10.0, None)
        assert upgrade_impact_with_cid("low", result) == "medium"

    def test_shared_use_no_upgrade(self):
        result = CIDResult("shared_use_path", "Shared use path", 10.0, None)
        assert upgrade_impact_with_cid("low", result) == "low"

    def test_stepped_cycleway_upgrades_to_high(self):
        result = CIDResult("stepped_cycleway", "Stepped cycle track", 10.0, None)
        assert upgrade_impact_with_cid("low", result) == "high"

    def test_partially_segregated_upgrades_to_high(self):
        result = CIDResult("partially_segregated_cycleway", "Partially segregated", 10.0, None)
        assert upgrade_impact_with_cid("medium", result) == "high"

    def test_contraflow_upgrades_to_medium(self):
        result = CIDResult("contraflow_lane", "Contraflow cycle lane", 10.0, None)
        assert upgrade_impact_with_cid("low", result) == "medium"
