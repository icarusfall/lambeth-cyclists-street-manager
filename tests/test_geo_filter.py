"""Tests for geo-filtering: coordinate conversion and borough matching."""

import pytest
from shapely.geometry import Point, Polygon

from src.geo.filter import GeoFilter, parse_bng_wkt_to_wgs84


class TestBngToWgs84:
    """Test British National Grid to WGS84 coordinate conversion."""

    def test_brixton_road_conversion(self):
        """Brixton Road BNG coords should convert to roughly -0.114, 51.462."""
        point = parse_bng_wkt_to_wgs84("POINT(531100.00 176100.00)")
        assert point is not None
        # Brixton Road is approximately at -0.114 lon, 51.462 lat
        assert -0.12 < point.x < -0.10  # longitude
        assert 51.45 < point.y < 51.48  # latitude

    def test_westminster_conversion(self):
        """Westminster BNG coords should convert to roughly -0.13, 51.50."""
        point = parse_bng_wkt_to_wgs84("POINT(530000.00 180000.00)")
        assert point is not None
        assert -0.15 < point.x < -0.10
        assert 51.49 < point.y < 51.52

    def test_invalid_wkt_returns_none(self):
        assert parse_bng_wkt_to_wgs84("INVALID") is None
        assert parse_bng_wkt_to_wgs84("") is None

    def test_polygon_returns_centroid(self):
        """POLYGON should return the centroid of the vertex coordinates."""
        # BNG polygon roughly in Westminster
        point = parse_bng_wkt_to_wgs84(
            "POLYGON((530000 180000,530100 180000,530100 180100,530000 180100,530000 180000))"
        )
        assert point is not None
        assert -0.15 < point.x < -0.10
        assert 51.49 < point.y < 51.52

    def test_linestring_returns_midpoint(self):
        """LINESTRING should return the midpoint of the coordinate list."""
        # Two BNG points roughly in Westminster
        point = parse_bng_wkt_to_wgs84(
            "LINESTRING(530000.00 180000.00,531000.00 180500.00)"
        )
        assert point is not None
        assert -0.15 < point.x < -0.10
        assert 51.49 < point.y < 51.52

    def test_activity_linestring_with_multiple_coords(self):
        """Real activity LINESTRING with multiple coordinate pairs."""
        wkt = "LINESTRING(531100.00 176100.00,531200.00 176200.00,531300.00 176300.00)"
        point = parse_bng_wkt_to_wgs84(wkt)
        assert point is not None


class TestGeoFilter:
    """Test the two-tier geo-filter."""

    @pytest.fixture
    def geo_filter(self):
        """Create a GeoFilter with a simple test polygon for Lambeth."""
        # A rough bounding-box polygon around Lambeth (WGS84)
        lambeth_poly = Polygon([
            (-0.15, 51.44),
            (-0.08, 51.44),
            (-0.08, 51.50),
            (-0.15, 51.50),
            (-0.15, 51.44),
        ])
        return GeoFilter({"Lambeth": lambeth_poly})

    def test_swa_code_fast_path(self, geo_filter):
        """Works by a target borough's highway authority should match immediately."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "5660",  # Lambeth
            "street_name": "TEST STREET",
        })
        assert include is True
        assert borough == "Lambeth"

    def test_tfl_road_in_lambeth_matches_via_geo(self, geo_filter):
        """TfL-managed roads in Lambeth should match via point-in-polygon."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "20",  # TfL
            "works_location_coordinates": "POINT(531100.00 176100.00)",  # Brixton Road
        })
        assert include is True
        assert borough == "Lambeth"

    def test_outside_all_boroughs_rejected(self, geo_filter):
        """Coordinates outside target boroughs should be rejected."""
        include, _ = geo_filter.check({
            "highway_authority_swa_code": "9999",  # Unknown authority
            "works_location_coordinates": "POINT(540000.00 190000.00)",  # East London
        })
        assert include is False

    def test_no_coordinates_non_target_swa_rejected(self, geo_filter):
        """Works with unknown SWA and no coordinates should be rejected."""
        include, _ = geo_filter.check({
            "highway_authority_swa_code": "9999",
        })
        assert include is False

    def test_unknown_swa_not_matched(self, geo_filter):
        """SWA codes not in our target list shouldn't fast-path match."""
        include, _ = geo_filter.check({
            "highway_authority_swa_code": "1234",  # Not a target borough
        })
        assert include is False

    def test_activity_coordinates_fallback(self, geo_filter):
        """Activities using activity_coordinates should be geo-filtered."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "20",  # TfL
            "activity_coordinates": "POINT(531100.00 176100.00)",  # Brixton Road
        })
        assert include is True
        assert borough == "Lambeth"

    def test_activity_linestring_in_lambeth(self, geo_filter):
        """Activity LINESTRING coordinates in Lambeth should match."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "20",
            "activity_coordinates": "LINESTRING(531100.00 176100.00,531200.00 176200.00)",
        })
        assert include is True
        assert borough == "Lambeth"
