-- PostGIS schema for South London Street Works Monitor
-- Run against Railway PostgreSQL: psql $DATABASE_URL -f sql/schema.sql

CREATE EXTENSION IF NOT EXISTS postgis;

-- Auto-update trigger function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Roadworks (Street Manager permits + activities)
CREATE TABLE IF NOT EXISTS roadworks (
    id                  SERIAL PRIMARY KEY,
    permit_reference    TEXT UNIQUE NOT NULL,
    name                TEXT,
    work_reference      TEXT,
    borough             TEXT NOT NULL,
    highway_authority   TEXT,
    street_name         TEXT,
    area                TEXT,
    usrn                TEXT,
    promoter            TEXT,
    work_category       TEXT,
    traffic_management  TEXT,
    work_status         TEXT,
    proposed_start      DATE,
    proposed_end        DATE,
    actual_start        DATE,
    ttro_required       BOOLEAN DEFAULT FALSE,
    cycling_impact      TEXT CHECK (cycling_impact IN ('High','Medium','Low','Minimal')),
    cycling_summary     TEXT,
    nearby_cycling_infra TEXT,
    activity_type       TEXT,
    source_event        TEXT,
    location            GEOMETRY(Point, 4326),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_roadworks_location ON roadworks USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_roadworks_borough ON roadworks (borough);
CREATE INDEX IF NOT EXISTS idx_roadworks_impact ON roadworks (cycling_impact);
CREATE INDEX IF NOT EXISTS idx_roadworks_status ON roadworks (work_status);

CREATE OR REPLACE TRIGGER trg_roadworks_updated_at
    BEFORE UPDATE ON roadworks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- TfL Disruptions
CREATE TABLE IF NOT EXISTS disruptions (
    id                  SERIAL PRIMARY KEY,
    disruption_id       TEXT UNIQUE NOT NULL,
    name                TEXT,
    borough             TEXT NOT NULL,
    category            TEXT,
    sub_category        TEXT,
    status              TEXT,
    severity            TEXT,
    location_desc       TEXT,
    corridors           TEXT,
    start_time          TIMESTAMPTZ,
    end_time            TIMESTAMPTZ,
    description         TEXT,
    cycling_impact      TEXT CHECK (cycling_impact IN ('High','Medium','Low','Minimal')),
    cycling_summary     TEXT,
    nearby_cycling_infra TEXT,
    location            GEOMETRY(Point, 4326),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_disruptions_location ON disruptions USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_disruptions_borough ON disruptions (borough);
CREATE INDEX IF NOT EXISTS idx_disruptions_status ON disruptions (status);

CREATE OR REPLACE TRIGGER trg_disruptions_updated_at
    BEFORE UPDATE ON disruptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Cycling Collisions (STATS19)
CREATE TABLE IF NOT EXISTS collisions (
    id                      SERIAL PRIMARY KEY,
    collision_reference     TEXT UNIQUE NOT NULL,
    name                    TEXT,
    borough                 TEXT NOT NULL,
    date                    DATE,
    time                    TEXT,
    severity                TEXT CHECK (severity IN ('Fatal','Serious','Slight')),
    number_of_cyclists_hurt INTEGER DEFAULT 0,
    worst_cyclist_severity  TEXT,
    other_vehicles          TEXT,
    road_name               TEXT,
    speed_limit             INTEGER,
    junction_detail         TEXT,
    light_conditions        TEXT,
    weather                 TEXT,
    road_surface            TEXT,
    data_year               TEXT,
    location                GEOMETRY(Point, 4326),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_collisions_location ON collisions USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_collisions_borough ON collisions (borough);
CREATE INDEX IF NOT EXISTS idx_collisions_severity ON collisions (severity);
CREATE INDEX IF NOT EXISTS idx_collisions_date ON collisions (date);

-- Traffic Orders (D-TRO)
CREATE TABLE IF NOT EXISTS traffic_orders (
    id                      SERIAL PRIMARY KEY,
    dtro_id                 TEXT UNIQUE NOT NULL,
    name                    TEXT,
    dtro_reference          TEXT,
    borough                 TEXT NOT NULL,
    regulation_type         TEXT[],
    location_description    TEXT,
    street_name             TEXT,
    made_date               DATE,
    effective_date          DATE,
    end_date                DATE,
    authority               TEXT,
    action_type             TEXT,
    cycling_impact          TEXT CHECK (cycling_impact IN ('Positive','Negative','Neutral','Needs Review')),
    cycling_summary         TEXT,
    nearby_cycling_infra    TEXT,
    schema_version          TEXT,
    location                GEOMETRY(Point, 4326),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_traffic_orders_location ON traffic_orders USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_traffic_orders_borough ON traffic_orders (borough);
CREATE INDEX IF NOT EXISTS idx_traffic_orders_impact ON traffic_orders (cycling_impact);

CREATE OR REPLACE TRIGGER trg_traffic_orders_updated_at
    BEFORE UPDATE ON traffic_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
