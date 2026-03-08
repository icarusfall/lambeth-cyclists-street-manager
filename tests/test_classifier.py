"""Tests for the rule-based cycling impact classifier."""

from src.classifier.rules import quick_cycling_impact


class TestQuickCyclingImpact:
    def test_road_closure_is_high(self):
        assert quick_cycling_impact({"traffic_management_type_ref": "road_closure"}) == "high"

    def test_lane_closure_is_high(self):
        assert quick_cycling_impact({"traffic_management_type_ref": "lane_closure"}) == "high"

    def test_multi_way_signals_is_medium(self):
        assert quick_cycling_impact({"traffic_management_type_ref": "multi_way_signals"}) == "medium"

    def test_two_way_signals_is_medium(self):
        assert quick_cycling_impact({"traffic_management_type_ref": "two_way_signals"}) == "medium"

    def test_emergency_works_is_medium(self):
        result = quick_cycling_impact({
            "traffic_management_type_ref": "some_carriageway_restriction",
            "work_category_ref": "immediate_emergency",
        })
        assert result == "medium"

    def test_footway_with_no_restriction_is_minimal(self):
        result = quick_cycling_impact({
            "traffic_management_type_ref": "no_carriageway_restriction",
            "works_location_type": "Footway",
        })
        assert result == "minimal"

    def test_carriageway_with_no_restriction_is_low(self):
        result = quick_cycling_impact({
            "traffic_management_type_ref": "no_carriageway_restriction",
            "works_location_type": "Carriageway",
        })
        assert result == "low"

    def test_unknown_traffic_management_is_low(self):
        assert quick_cycling_impact({}) == "low"
