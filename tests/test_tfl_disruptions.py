"""Tests for TfL disruptions integration."""

import pytest
from shapely.geometry import Point

from src.tfl.disruptions import classify_disruption_impact, extract_point
from src.db.schemas import disruption_to_db_row


class TestClassifyDisruptionImpact:
    def test_collision_is_high(self):
        assert classify_disruption_impact({"category": "Collisions"}) == "high"

    def test_hazard_is_high(self):
        assert classify_disruption_impact({"category": "Hazards"}) == "high"

    def test_serious_severity_is_high(self):
        assert classify_disruption_impact(
            {"category": "Works", "severity": "Serious"}
        ) == "high"

    def test_moderate_works_is_medium(self):
        assert classify_disruption_impact(
            {"category": "Works", "severity": "Moderate"}
        ) == "medium"

    def test_breakdown_is_medium(self):
        assert classify_disruption_impact({"category": "Breakdowns"}) == "medium"

    def test_planned_event_is_medium(self):
        assert classify_disruption_impact({"category": "Planned events"}) == "medium"

    def test_network_delays_is_medium(self):
        assert classify_disruption_impact({"category": "Network delays"}) == "medium"

    def test_minimal_works_is_low(self):
        assert classify_disruption_impact(
            {"category": "Works", "severity": "Minimal"}
        ) == "low"

    def test_unknown_category_is_low(self):
        assert classify_disruption_impact({"category": "SomethingNew"}) == "low"

    def test_empty_disruption_is_low(self):
        assert classify_disruption_impact({}) == "low"


class TestExtractPoint:
    def test_point_geometry(self):
        disruption = {
            "geography": {"type": "Point", "coordinates": [-0.1178, 51.4613]}
        }
        point = extract_point(disruption)
        assert point is not None
        assert abs(point.x - (-0.1178)) < 0.001
        assert abs(point.y - 51.4613) < 0.001

    def test_linestring_uses_centroid(self):
        disruption = {
            "geography": {
                "type": "LineString",
                "coordinates": [[-0.1, 51.46], [-0.12, 51.47]],
            }
        }
        point = extract_point(disruption)
        assert point is not None
        # Centroid should be roughly between the two points
        assert -0.13 < point.x < -0.09
        assert 51.45 < point.y < 51.48

    def test_no_geography_returns_none(self):
        assert extract_point({}) is None

    def test_null_geography_returns_none(self):
        assert extract_point({"geography": None}) is None


class TestDisruptionDbRow:
    def test_basic_mapping(self):
        disruption = {
            "id": "TIMS-12345",
            "location": "Brixton Road",
            "category": "Collisions",
            "status": "Active",
            "severity": "Serious",
            "subCategory": "Burst water main",
            "comments": "Road closed due to flooding",
            "corridors": [{"name": "A23"}, {"name": "A204"}],
            "startDateTime": "2026-03-09T10:00:00Z",
            "endDateTime": "2026-03-10T18:00:00Z",
        }
        row = disruption_to_db_row(
            disruption=disruption,
            borough="Lambeth",
            cycling_impact="high",
            wgs84_coords="-0.1178,51.4613",
        )

        assert row["name"] == "Brixton Road — Collisions"
        assert row["disruption_id"] == "TIMS-12345"
        assert row["borough"] == "Lambeth"
        assert row["category"] == "Collisions"
        assert row["status"] == "Active"
        assert row["severity"] == "Serious"
        assert row["corridors"] == "A23, A204"
        assert row["cycling_impact"] == "High"
        assert row["lon"] == pytest.approx(-0.1178)
        assert row["lat"] == pytest.approx(51.4613)

    def test_missing_fields_handled(self):
        row = disruption_to_db_row(
            disruption={"id": "TEST-1"},
            borough="Southwark",
            cycling_impact="low",
        )
        assert row["name"] == "Unknown location — Other"
        assert row["borough"] == "Southwark"
        assert row["cycling_summary"] is None
        assert row["lon"] is None

    def test_cycling_summary_included(self):
        row = disruption_to_db_row(
            disruption={"id": "TEST-2", "location": "Test Road"},
            borough="Lambeth",
            cycling_impact="high",
            cycling_summary="Major impact on cyclists due to road closure.",
        )
        assert row["cycling_summary"] == "Major impact on cyclists due to road closure."
