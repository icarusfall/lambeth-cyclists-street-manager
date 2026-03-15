"""PostgreSQL database writer using asyncpg."""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseWriter:
    """Writes records to PostgreSQL using asyncpg connection pool."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create the connection pool."""
        self._pool = await asyncpg.create_pool(self._database_url, min_size=2, max_size=10)
        logger.info("PostgreSQL connection pool created")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def upsert_roadwork(self, permit_ref: str, data: dict) -> str | None:
        """Insert or update a roadwork record. Returns row ID as string."""
        try:
            row = await self._pool.fetchrow(
                """
                INSERT INTO roadworks (
                    permit_reference, name, work_reference, borough,
                    highway_authority, street_name, area, usrn, promoter,
                    work_category, traffic_management, work_status,
                    proposed_start, proposed_end, actual_start,
                    ttro_required, cycling_impact, cycling_summary,
                    nearby_cycling_infra, activity_type, source_event,
                    lon, lat
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13::date, $14::date, $15::date,
                    $16, $17, $18, $19, $20, $21, $22, $23
                )
                ON CONFLICT (permit_reference) DO UPDATE SET
                    name = EXCLUDED.name,
                    work_reference = EXCLUDED.work_reference,
                    borough = EXCLUDED.borough,
                    highway_authority = EXCLUDED.highway_authority,
                    street_name = EXCLUDED.street_name,
                    area = EXCLUDED.area,
                    usrn = EXCLUDED.usrn,
                    promoter = EXCLUDED.promoter,
                    work_category = EXCLUDED.work_category,
                    traffic_management = EXCLUDED.traffic_management,
                    work_status = EXCLUDED.work_status,
                    proposed_start = EXCLUDED.proposed_start,
                    proposed_end = EXCLUDED.proposed_end,
                    actual_start = EXCLUDED.actual_start,
                    ttro_required = EXCLUDED.ttro_required,
                    cycling_impact = EXCLUDED.cycling_impact,
                    cycling_summary = EXCLUDED.cycling_summary,
                    nearby_cycling_infra = EXCLUDED.nearby_cycling_infra,
                    activity_type = EXCLUDED.activity_type,
                    source_event = EXCLUDED.source_event,
                    lon = COALESCE(EXCLUDED.lon, roadworks.lon),
                    lat = COALESCE(EXCLUDED.lat, roadworks.lat)
                RETURNING id
                """,
                permit_ref, data.get("name"), data.get("work_reference"),
                data.get("borough"), data.get("highway_authority"),
                data.get("street_name"), data.get("area"), data.get("usrn"),
                data.get("promoter"), data.get("work_category"),
                data.get("traffic_management"), data.get("work_status"),
                data.get("proposed_start"), data.get("proposed_end"),
                data.get("actual_start"), data.get("ttro_required", False),
                data.get("cycling_impact"), data.get("cycling_summary"),
                data.get("nearby_cycling_infra"),
                data.get("activity_type"), data.get("source_event"),
                data.get("lon"), data.get("lat"),
            )
            logger.info("Upserted roadwork %s (id=%s)", permit_ref, row["id"])
            return str(row["id"])
        except Exception:
            logger.exception("Failed to upsert roadwork %s", permit_ref)
            return None

    async def upsert_disruption(self, disruption_id: str, data: dict) -> str | None:
        """Insert or update a TfL disruption record."""
        try:
            row = await self._pool.fetchrow(
                """
                INSERT INTO disruptions (
                    disruption_id, name, borough, category, sub_category,
                    status, severity, location_desc, corridors,
                    start_time, end_time, description,
                    cycling_impact, cycling_summary, nearby_cycling_infra,
                    lon, lat
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10::timestamptz, $11::timestamptz, $12,
                    $13, $14, $15, $16, $17
                )
                ON CONFLICT (disruption_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    borough = EXCLUDED.borough,
                    category = EXCLUDED.category,
                    sub_category = EXCLUDED.sub_category,
                    status = EXCLUDED.status,
                    severity = EXCLUDED.severity,
                    location_desc = EXCLUDED.location_desc,
                    corridors = EXCLUDED.corridors,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    description = EXCLUDED.description,
                    cycling_impact = EXCLUDED.cycling_impact,
                    cycling_summary = EXCLUDED.cycling_summary,
                    nearby_cycling_infra = EXCLUDED.nearby_cycling_infra,
                    lon = COALESCE(EXCLUDED.lon, disruptions.lon),
                    lat = COALESCE(EXCLUDED.lat, disruptions.lat)
                RETURNING id
                """,
                disruption_id, data.get("name"), data.get("borough"),
                data.get("category"), data.get("sub_category"),
                data.get("status"), data.get("severity"),
                data.get("location_desc"), data.get("corridors"),
                data.get("start_time"), data.get("end_time"),
                data.get("description"), data.get("cycling_impact"),
                data.get("cycling_summary"),
                data.get("nearby_cycling_infra"),
                data.get("lon"), data.get("lat"),
            )
            logger.info("Upserted disruption %s (id=%s)", disruption_id, row["id"])
            return str(row["id"])
        except Exception:
            logger.exception("Failed to upsert disruption %s", disruption_id)
            return None

    async def upsert_collision(self, collision_ref: str, data: dict) -> str | None:
        """Insert or update a collision record."""
        try:
            row = await self._pool.fetchrow(
                """
                INSERT INTO collisions (
                    collision_reference, name, borough, date, time,
                    severity, number_of_cyclists_hurt, worst_cyclist_severity,
                    other_vehicles, road_name, speed_limit, junction_detail,
                    light_conditions, weather, road_surface, data_year,
                    lon, lat
                ) VALUES (
                    $1, $2, $3, $4::date, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18
                )
                ON CONFLICT (collision_reference) DO UPDATE SET
                    name = EXCLUDED.name,
                    borough = EXCLUDED.borough,
                    date = EXCLUDED.date,
                    time = EXCLUDED.time,
                    severity = EXCLUDED.severity,
                    number_of_cyclists_hurt = EXCLUDED.number_of_cyclists_hurt,
                    worst_cyclist_severity = EXCLUDED.worst_cyclist_severity,
                    other_vehicles = EXCLUDED.other_vehicles,
                    road_name = EXCLUDED.road_name,
                    speed_limit = EXCLUDED.speed_limit,
                    junction_detail = EXCLUDED.junction_detail,
                    light_conditions = EXCLUDED.light_conditions,
                    weather = EXCLUDED.weather,
                    road_surface = EXCLUDED.road_surface,
                    data_year = EXCLUDED.data_year,
                    lon = COALESCE(EXCLUDED.lon, collisions.lon),
                    lat = COALESCE(EXCLUDED.lat, collisions.lat)
                RETURNING id
                """,
                collision_ref, data.get("name"), data.get("borough"),
                data.get("date"), data.get("time"),
                data.get("severity"), data.get("number_of_cyclists_hurt", 0),
                data.get("worst_cyclist_severity"), data.get("other_vehicles"),
                data.get("road_name"), data.get("speed_limit"),
                data.get("junction_detail"), data.get("light_conditions"),
                data.get("weather"), data.get("road_surface"),
                data.get("data_year"),
                data.get("lon"), data.get("lat"),
            )
            logger.info("Upserted collision %s (id=%s)", collision_ref, row["id"])
            return str(row["id"])
        except Exception:
            logger.exception("Failed to upsert collision %s", collision_ref)
            return None

    async def upsert_traffic_order(self, dtro_id: str, data: dict) -> str | None:
        """Insert or update a traffic order record."""
        try:
            row = await self._pool.fetchrow(
                """
                INSERT INTO traffic_orders (
                    dtro_id, name, dtro_reference, borough, regulation_type,
                    location_description, street_name, made_date, effective_date,
                    end_date, authority, action_type,
                    cycling_impact, cycling_summary, nearby_cycling_infra,
                    schema_version, lon, lat
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8::date, $9::date, $10::date,
                    $11, $12, $13, $14, $15, $16, $17, $18
                )
                ON CONFLICT (dtro_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    dtro_reference = EXCLUDED.dtro_reference,
                    borough = EXCLUDED.borough,
                    regulation_type = EXCLUDED.regulation_type,
                    location_description = EXCLUDED.location_description,
                    street_name = EXCLUDED.street_name,
                    made_date = EXCLUDED.made_date,
                    effective_date = EXCLUDED.effective_date,
                    end_date = EXCLUDED.end_date,
                    authority = EXCLUDED.authority,
                    action_type = EXCLUDED.action_type,
                    cycling_impact = EXCLUDED.cycling_impact,
                    cycling_summary = EXCLUDED.cycling_summary,
                    nearby_cycling_infra = EXCLUDED.nearby_cycling_infra,
                    schema_version = EXCLUDED.schema_version,
                    lon = COALESCE(EXCLUDED.lon, traffic_orders.lon),
                    lat = COALESCE(EXCLUDED.lat, traffic_orders.lat)
                RETURNING id
                """,
                dtro_id, data.get("name"), data.get("dtro_reference"),
                data.get("borough"), data.get("regulation_type", []),
                data.get("location_description"), data.get("street_name"),
                data.get("made_date"), data.get("effective_date"),
                data.get("end_date"), data.get("authority"),
                data.get("action_type"), data.get("cycling_impact"),
                data.get("cycling_summary"),
                data.get("nearby_cycling_infra"), data.get("schema_version"),
                data.get("lon"), data.get("lat"),
            )
            logger.info("Upserted traffic order %s (id=%s)", dtro_id, row["id"])
            return str(row["id"])
        except Exception:
            logger.exception("Failed to upsert traffic order %s", dtro_id)
            return None

    async def mark_resolved_disruptions(self, active_ids: set[str]) -> None:
        """Mark disruptions as Resolved if they're no longer in the TfL feed."""
        if not active_ids:
            return
        try:
            result = await self._pool.execute(
                """
                UPDATE disruptions SET status = 'Resolved'
                WHERE disruption_id != ALL($1::text[])
                AND status != 'Resolved'
                """,
                list(active_ids),
            )
            logger.info("Mark resolved disruptions: %s", result)
        except Exception:
            logger.exception("Failed to mark resolved disruptions")
