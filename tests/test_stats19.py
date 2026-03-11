"""Tests for STATS19 cycling collision importer."""

import pytest
from shapely.geometry import Point, Polygon

from src.geo.filter import GeoFilter
from src.stats19.importer import (
    CyclistCollision,
    filter_cycling_collisions,
    SEVERITY_LABELS,
    VEHICLE_TYPE_LABELS,
    LIGHT_CONDITIONS_LABELS,
    WEATHER_LABELS,
    ROAD_SURFACE_LABELS,
)
from src.notion.schemas import collision_to_notion_properties


@pytest.fixture
def geo_filter():
    """GeoFilter with a rough Lambeth bounding box."""
    lambeth_poly = Polygon([
        (-0.15, 51.44),
        (-0.08, 51.44),
        (-0.08, 51.50),
        (-0.15, 51.50),
        (-0.15, 51.44),
    ])
    return GeoFilter({"Lambeth": lambeth_poly})


def _make_collision(collision_index="2024001", lat="51.46", lon="-0.11",
                    severity="2", date="01/07/2024", time="14:30",
                    speed_limit="30", road_class="3", road_number="23",
                    junction_detail="13", light="1", weather="1",
                    surface="1", year="2024"):
    return {
        "collision_index": collision_index,
        "latitude": lat,
        "longitude": lon,
        "collision_severity": severity,
        "date": date,
        "time": time,
        "speed_limit": speed_limit,
        "first_road_class": road_class,
        "first_road_number": road_number,
        "junction_detail": junction_detail,
        "light_conditions": light,
        "weather_conditions": weather,
        "road_surface_conditions": surface,
        "collision_year": year,
    }


def _make_casualty(collision_index="2024001", casualty_type="1",
                   casualty_severity="2", vehicle_reference="1",
                   casualty_reference="1"):
    return {
        "collision_index": collision_index,
        "casualty_type": casualty_type,
        "casualty_severity": casualty_severity,
        "vehicle_reference": vehicle_reference,
        "casualty_reference": casualty_reference,
    }


def _make_vehicle(collision_index="2024001", vehicle_type="9",
                  vehicle_reference="2"):
    return {
        "collision_index": collision_index,
        "vehicle_type": vehicle_type,
        "vehicle_reference": vehicle_reference,
    }


class TestFilterCyclingCollisions:
    def test_basic_cyclist_collision_in_lambeth(self, geo_filter):
        """Collision with cyclist casualty in Lambeth should be included."""
        collisions = [_make_collision()]
        casualties = [_make_casualty()]
        vehicles = [
            _make_vehicle(vehicle_type="1", vehicle_reference="1"),  # Cyclist
            _make_vehicle(vehicle_type="9", vehicle_reference="2"),  # Car
        ]

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert len(results) == 1
        assert results[0].borough == "Lambeth"
        assert results[0].num_cyclist_casualties == 1
        assert results[0].other_vehicles == ["Car"]

    def test_collision_outside_borough_excluded(self, geo_filter):
        """Collision outside target boroughs should be excluded."""
        collisions = [_make_collision(lat="51.55", lon="0.05")]  # East London
        casualties = [_make_casualty()]
        vehicles = []

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert len(results) == 0

    def test_non_cyclist_collision_excluded(self, geo_filter):
        """Collision without cyclist casualties should be excluded."""
        collisions = [_make_collision()]
        casualties = [_make_casualty(casualty_type="9")]  # Car occupant
        vehicles = []

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert len(results) == 0

    def test_multiple_cyclist_casualties(self, geo_filter):
        """Multiple cyclist casualties in one collision."""
        collisions = [_make_collision()]
        casualties = [
            _make_casualty(casualty_reference="1", casualty_severity="3"),
            _make_casualty(casualty_reference="2", casualty_severity="1"),  # Fatal
        ]
        vehicles = []

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert len(results) == 1
        assert results[0].num_cyclist_casualties == 2
        assert results[0].worst_cyclist_severity == "Fatal"

    def test_severity_labels(self, geo_filter):
        """Severity codes should be mapped to labels."""
        collisions = [_make_collision(severity="1")]
        casualties = [_make_casualty(casualty_severity="1")]
        vehicles = []

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert results[0].collision_severity == "Fatal"
        assert results[0].worst_cyclist_severity == "Fatal"

    def test_multiple_other_vehicles_deduped(self, geo_filter):
        """Multiple cars should appear once in other_vehicles."""
        collisions = [_make_collision()]
        casualties = [_make_casualty()]
        vehicles = [
            _make_vehicle(vehicle_type="1", vehicle_reference="1"),
            _make_vehicle(vehicle_type="9", vehicle_reference="2"),
            _make_vehicle(vehicle_type="9", vehicle_reference="3"),
        ]

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert results[0].other_vehicles == ["Car"]

    def test_hgv_and_car_vehicles(self, geo_filter):
        """HGV and car should both appear in other_vehicles."""
        collisions = [_make_collision()]
        casualties = [_make_casualty()]
        vehicles = [
            _make_vehicle(vehicle_type="1", vehicle_reference="1"),
            _make_vehicle(vehicle_type="21", vehicle_reference="2"),  # HGV
            _make_vehicle(vehicle_type="9", vehicle_reference="3"),   # Car
        ]

        results = filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
        assert "HGV" in results[0].other_vehicles
        assert "Car" in results[0].other_vehicles

    def test_road_name_from_class_and_number(self, geo_filter):
        """Road name should be built from road class + number."""
        collisions = [_make_collision(road_class="3", road_number="23")]
        casualties = [_make_casualty()]

        results = filter_cycling_collisions(collisions, casualties, [], geo_filter)
        assert results[0].road_name == "A23"

    def test_missing_coordinates_excluded(self, geo_filter):
        """Collisions without coordinates should be excluded."""
        collisions = [_make_collision(lat="", lon="")]
        casualties = [_make_casualty()]

        results = filter_cycling_collisions(collisions, casualties, [], geo_filter)
        assert len(results) == 0


class TestCollisionNotionProperties:
    def test_basic_mapping(self):
        collision = CyclistCollision(
            collision_index="2024001",
            date="01/07/2024",
            time="14:30",
            latitude=51.46,
            longitude=-0.11,
            borough="Lambeth",
            collision_severity="Serious",
            num_cyclist_casualties=1,
            worst_cyclist_severity="Serious",
            other_vehicles=["Car"],
            road_name="A23",
            speed_limit=30,
            junction_detail="T or staggered junction",
            light_conditions="Daylight",
            weather="Fine",
            road_surface="Dry",
            data_year="2024",
        )

        props = collision_to_notion_properties(collision)
        assert props["Name"]["title"][0]["text"]["content"] == "A23 — 01/07/2024"
        assert props["Borough"]["select"]["name"] == "Lambeth"
        assert props["Severity"]["select"]["name"] == "Serious"
        assert props["Number of Cyclists Hurt"]["number"] == 1
        assert props["Other Vehicles"]["rich_text"][0]["text"]["content"] == "Car"
        assert props["Speed Limit"]["number"] == 30
        assert props["Data Year"]["rich_text"][0]["text"]["content"] == "2024"

    def test_no_road_name_uses_unknown(self):
        collision = CyclistCollision(
            collision_index="2024002",
            date="01/07/2024",
            time="14:30",
            latitude=51.46,
            longitude=-0.11,
            borough="Lambeth",
            collision_severity="Slight",
            num_cyclist_casualties=1,
            worst_cyclist_severity="Slight",
            other_vehicles=[],
            road_name="",
            speed_limit=20,
            junction_detail="Not at junction",
            light_conditions="Daylight",
            weather="Fine",
            road_surface="Dry",
            data_year="2024",
        )

        props = collision_to_notion_properties(collision)
        assert props["Name"]["title"][0]["text"]["content"] == "Unknown road — 01/07/2024"
        assert props["Other Vehicles"]["rich_text"][0]["text"]["content"] == "None"


class TestLookupTables:
    def test_severity_labels_complete(self):
        assert SEVERITY_LABELS[1] == "Fatal"
        assert SEVERITY_LABELS[2] == "Serious"
        assert SEVERITY_LABELS[3] == "Slight"

    def test_vehicle_type_labels(self):
        assert VEHICLE_TYPE_LABELS[1] == "Pedal cycle"
        assert VEHICLE_TYPE_LABELS[9] == "Car"
        assert VEHICLE_TYPE_LABELS[21] == "HGV"
        assert VEHICLE_TYPE_LABELS[11] == "Bus/Coach"

    def test_weather_labels(self):
        assert WEATHER_LABELS[1] == "Fine"
        assert WEATHER_LABELS[2] == "Rain"
