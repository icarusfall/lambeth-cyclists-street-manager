"""Tests for PostgreSQL database schemas and writer."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.schemas import (
    collision_to_db_row,
    disruption_to_db_row,
    traffic_order_to_db_row,
    work_to_db_row,
)
from src.db.writer import DatabaseWriter


# --- Schema mapper tests ---


class TestWorkToDbRow:
    def test_basic_mapping(self):
        object_data = {
            "permit_reference_number": "TEST-001",
            "work_reference_number": "WORK-001",
            "street_name": "BRIXTON ROAD",
            "area_name": "BRIXTON",
            "highway_authority": "LONDON BOROUGH OF LAMBETH",
            "promoter_organisation": "Thames Water",
            "usrn": "22500123",
            "work_category_ref": "minor",
            "traffic_management_type_ref": "road_closure",
            "work_status_ref": "in_progress",
            "proposed_start_date": "2026-03-10T00:00:00.000Z",
            "proposed_end_date": "2026-03-14T00:00:00.000Z",
            "activity_type": "Utility repair and maintenance works",
            "is_ttro_required": "Yes",
        }

        row = work_to_db_row(
            object_data=object_data,
            borough="Lambeth",
            cycling_impact="high",
            cycling_summary="Major disruption on key cycling corridor.",
            event_type="WORK_START",
            wgs84_coords="-0.114000,51.462000",
        )

        assert row["permit_reference"] == "TEST-001"
        assert row["name"] == "BRIXTON ROAD, BRIXTON"
        assert row["borough"] == "Lambeth"
        assert row["work_category"] == "Minor"
        assert row["traffic_management"] == "Road closure"
        assert row["work_status"] == "In progress"
        assert row["cycling_impact"] == "High"
        assert row["cycling_summary"] == "Major disruption on key cycling corridor."
        assert row["ttro_required"] is True
        assert row["proposed_start"] == "2026-03-10"
        assert row["lon"] == pytest.approx(-0.114)
        assert row["lat"] == pytest.approx(51.462)

    def test_missing_area_name(self):
        row = work_to_db_row(
            object_data={"street_name": "HIGH STREET"},
            borough="Southwark",
            cycling_impact="low",
            cycling_summary=None,
            event_type="PERMIT_GRANTED",
        )
        assert row["name"] == "HIGH STREET"
        assert row["cycling_summary"] is None

    def test_no_coordinates(self):
        row = work_to_db_row(
            object_data={},
            borough="Wandsworth",
            cycling_impact="minimal",
            cycling_summary=None,
            event_type="PERMIT_GRANTED",
        )
        assert row["lon"] is None
        assert row["lat"] is None


class TestDisruptionToDbRow:
    def test_basic_mapping(self):
        disruption = {
            "id": "TTIS-12345",
            "location": "Tower Bridge Road",
            "category": "Works",
            "subCategory": "Roadworks",
            "status": "Active",
            "severity": "Serious",
            "comments": "Road closed for maintenance",
            "startDateTime": "2026-03-10T08:00:00Z",
            "endDateTime": "2026-03-14T18:00:00Z",
            "corridors": [{"name": "A100"}],
        }

        row = disruption_to_db_row(
            disruption=disruption,
            borough="Southwark",
            cycling_impact="high",
            cycling_summary="Major disruption",
            wgs84_coords="-0.075000,51.505000",
        )

        assert row["disruption_id"] == "TTIS-12345"
        assert row["name"] == "Tower Bridge Road — Works"
        assert row["borough"] == "Southwark"
        assert row["category"] == "Works"
        assert row["status"] == "Active"
        assert row["corridors"] == "A100"
        assert row["lon"] == pytest.approx(-0.075)
        assert row["lat"] == pytest.approx(51.505)


class TestCollisionToDbRow:
    def test_basic_mapping(self):
        @dataclass
        class FakeCollision:
            collision_index: str = "2024010012345"
            date: str = "15/06/2024"
            time: str = "14:30"
            latitude: float = 51.462
            longitude: float = -0.114
            borough: str = "Lambeth"
            collision_severity: str = "Serious"
            num_cyclist_casualties: int = 1
            worst_cyclist_severity: str = "Serious"
            other_vehicles: list = None
            road_name: str = "BRIXTON ROAD"
            speed_limit: int = 30
            junction_detail: str = "T-junction"
            light_conditions: str = "Daylight"
            weather: str = "Fine"
            road_surface: str = "Dry"
            data_year: str = "2024"

            def __post_init__(self):
                if self.other_vehicles is None:
                    self.other_vehicles = ["Car", "Bus"]

        collision = FakeCollision()
        row = collision_to_db_row(collision)

        assert row["collision_reference"] == "2024010012345"
        assert row["name"] == "BRIXTON ROAD — 15/06/2024"
        assert row["date"] == "2024-06-15"
        assert row["severity"] == "Serious"
        assert row["number_of_cyclists_hurt"] == 1
        assert row["other_vehicles"] == "Car, Bus"
        assert row["lon"] == pytest.approx(-0.114)
        assert row["lat"] == pytest.approx(51.462)


class TestTrafficOrderToDbRow:
    def test_basic_mapping(self):
        details = {
            "dtro_id": "abc-123",
            "tro_name": "Lambeth (Cressingham Road) (No Right Turn)",
            "reference": "2024/TRO/001",
            "tra_name": "London Borough of Lambeth",
            "action_type": "new",
            "made_date": "2026-01-15",
            "effective_date": "2026-02-01",
            "regulation_types": ["miscOneWay"],
            "street_names": ["CRESSINGHAM ROAD"],
            "coordinates": "-0.114000,51.462000",
            "schema_version": "3.3.1",
            "regulation_end": "2026-06-01",
            "provision_description": "No right turn",
        }

        row = traffic_order_to_db_row(
            details=details,
            borough="Lambeth",
            cycling_impact="Negative",
            cycling_summary="One-way restriction on cycling corridor.",
        )

        assert row["dtro_id"] == "abc-123"
        assert row["name"] == "Lambeth (Cressingham Road) (No Right Turn)"
        assert row["borough"] == "Lambeth"
        assert row["regulation_type"] == ["miscOneWay"]
        assert row["cycling_impact"] == "Negative"
        assert row["end_date"] == "2026-06-01"
        assert row["lon"] == pytest.approx(-0.114)


# --- Writer mock tests ---


class TestDatabaseWriter:
    @pytest.fixture
    def writer(self):
        return DatabaseWriter("postgresql://test:test@localhost/test")

    @pytest.mark.asyncio
    async def test_upsert_roadwork_success(self, writer):
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={"id": 42})
        writer._pool = mock_pool

        result = await writer.upsert_roadwork("TEST-001", {
            "name": "Test Road",
            "borough": "Lambeth",
            "lon": -0.114,
            "lat": 51.462,
        })

        assert result == "42"
        mock_pool.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_roadwork_failure(self, writer):
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(side_effect=Exception("DB error"))
        writer._pool = mock_pool

        result = await writer.upsert_roadwork("TEST-001", {
            "name": "Test Road",
            "borough": "Lambeth",
        })

        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_disruption_success(self, writer):
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={"id": 7})
        writer._pool = mock_pool

        result = await writer.upsert_disruption("TTIS-123", {
            "name": "Test Disruption",
            "borough": "Southwark",
            "lon": -0.075,
            "lat": 51.505,
        })

        assert result == "7"

    @pytest.mark.asyncio
    async def test_upsert_collision_success(self, writer):
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={"id": 99})
        writer._pool = mock_pool

        result = await writer.upsert_collision("2024010012345", {
            "name": "BRIXTON ROAD — 15/06/2024",
            "borough": "Lambeth",
            "lon": -0.114,
            "lat": 51.462,
        })

        assert result == "99"

    @pytest.mark.asyncio
    async def test_upsert_traffic_order_success(self, writer):
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={"id": 5})
        writer._pool = mock_pool

        result = await writer.upsert_traffic_order("abc-123", {
            "name": "Test TRO",
            "borough": "Lambeth",
            "regulation_type": ["miscOneWay"],
            "lon": -0.114,
            "lat": 51.462,
        })

        assert result == "5"

    @pytest.mark.asyncio
    async def test_mark_resolved_disruptions(self, writer):
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock(return_value="UPDATE 3")
        writer._pool = mock_pool

        await writer.mark_resolved_disruptions({"id1", "id2"})
        mock_pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_and_close(self):
        with patch("src.db.writer.asyncpg") as mock_asyncpg:
            mock_pool = AsyncMock()
            mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

            writer = DatabaseWriter("postgresql://test:test@localhost/test")
            await writer.connect()
            assert writer._pool == mock_pool

            await writer.close()
            mock_pool.close.assert_called_once()
