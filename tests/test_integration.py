"""Integration tests using real borough boundary data."""

from pathlib import Path

import pytest

from src.geo.boundaries import load_borough_polygons
from src.geo.filter import GeoFilter

DATA_DIR = Path(__file__).parent.parent / "data"
GEOJSON_PATH = DATA_DIR / "london_boroughs.geojson"

TARGET_BOROUGHS = [
    "Lambeth", "Southwark", "Wandsworth", "Lewisham",
    "Merton", "Croydon", "City of London", "Westminster",
]


@pytest.fixture
def geo_filter():
    """GeoFilter using real borough boundaries."""
    if not GEOJSON_PATH.exists():
        pytest.skip("Borough boundary GeoJSON not available")
    polygons = load_borough_polygons(str(GEOJSON_PATH), TARGET_BOROUGHS)
    return GeoFilter(polygons)


class TestRealBoundaries:
    def test_all_boroughs_loaded(self):
        if not GEOJSON_PATH.exists():
            pytest.skip("Borough boundary GeoJSON not available")
        polygons = load_borough_polygons(str(GEOJSON_PATH), TARGET_BOROUGHS)
        assert len(polygons) == 8

    def test_brixton_road_is_lambeth(self, geo_filter):
        """Brixton Road (A23, TfL TLRN) — should geo-match to Lambeth."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "0999",  # TfL
            "works_location_coordinates": "POINT(531100.00 176100.00)",
        })
        assert include is True
        assert borough == "Lambeth"

    def test_borough_high_street_is_southwark(self, geo_filter):
        """Borough High Street — should match Southwark."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "0999",
            "works_location_coordinates": "POINT(532600.00 180100.00)",
        })
        assert include is True
        assert borough == "Southwark"

    def test_streatham_high_road_is_lambeth(self, geo_filter):
        """Streatham High Road — should match Lambeth."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "0999",
            "works_location_coordinates": "POINT(530300.00 171200.00)",
        })
        assert include is True
        assert borough == "Lambeth"

    def test_croydon_town_centre(self, geo_filter):
        """Croydon town centre — should match Croydon."""
        include, borough = geo_filter.check({
            "highway_authority_swa_code": "0999",
            "works_location_coordinates": "POINT(532600.00 165300.00)",
        })
        assert include is True
        assert borough == "Croydon"

    def test_canary_wharf_rejected(self, geo_filter):
        """Canary Wharf (Tower Hamlets) — should NOT match any target borough."""
        include, _ = geo_filter.check({
            "highway_authority_swa_code": "0999",
            "works_location_coordinates": "POINT(537900.00 180300.00)",
        })
        assert include is False

    def test_islington_rejected(self, geo_filter):
        """Islington — should NOT match any target borough."""
        include, _ = geo_filter.check({
            "highway_authority_swa_code": "0999",
            "works_location_coordinates": "POINT(531500.00 183500.00)",
        })
        assert include is False
