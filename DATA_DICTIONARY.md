# LCC South London — Data Dictionary

**Purpose:** Reference document for downstream projects (dashboards, visualisations, map overlays) that consume data produced by the Street Works Monitor pipeline.

**Data store:** PostgreSQL on Railway
**Pipeline repo:** https://github.com/icarusfall/lambeth-cyclists-street-manager
**Live endpoint:** https://lambeth-cyclists-street-manager-production.up.railway.app
**Health check:** `GET /health` returns JSON with pipeline status, poll counts, and uptime

---

## Coverage

All tables cover **8 south/central London boroughs:**
Lambeth, Southwark, Wandsworth, Lewisham, Merton, Croydon, City of London, Westminster

---

## Connection

**Environment variable:** `DATABASE_URL`
**Format:** `postgresql://user:pass@host:port/dbname`
**Driver:** Any PostgreSQL client (asyncpg, psycopg2, pg, Prisma, etc.)

The Railway Postgres instance is accessible from the public internet. For the visualiser, use a read-only connection or the same `DATABASE_URL`.

---

## 1. Roadworks (`roadworks` table)

**Update cadence:** Real-time (SNS push from DfT Street Manager)
**Primary key:** `id` (auto-increment)
**Dedup key:** `permit_reference` (UNIQUE)
**Approximate volume:** Growing daily from live notifications

### Columns

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| id | SERIAL | no | Auto-increment primary key | 1 |
| permit_reference | TEXT | no | Unique DfT permit/activity ref | "XX058005100648583-01" |
| name | TEXT | yes | Street name and area | "Brixton Road, Lambeth" |
| work_reference | TEXT | yes | Parent work reference | "XX058005100648583" |
| borough | TEXT | no | Geo-filtered borough | "Lambeth" |
| highway_authority | TEXT | yes | Responsible highway authority | "Transport for London" |
| street_name | TEXT | yes | Street where works take place | "Brixton Road" |
| area | TEXT | yes | Area/town name | "Lambeth" |
| usrn | TEXT | yes | Unique Street Reference Number | "20500753" |
| promoter | TEXT | yes | Organisation doing the works | "Thames Water Utilities Ltd" |
| work_category | TEXT | yes | Scale of works | "Major", "Standard", "Minor", "Immediate Urgent", "Immediate Emergency" |
| traffic_management | TEXT | yes | Type of traffic control | "Road closure", "Lane closure", "Multi-way signals", "Two-way signals", "Convoy working", "Give and take", "Some carriageway restriction", "No carriageway restriction" |
| work_status | TEXT | yes | Current status | "Planned", "In progress", "Completed", "Cancelled" |
| proposed_start | DATE | yes | Planned start date | 2026-03-15 |
| proposed_end | DATE | yes | Planned end date | 2026-03-20 |
| actual_start | DATE | yes | When works actually started | 2026-03-15 |
| ttro_required | BOOLEAN | no | Temporary Traffic Regulation Order needed | true/false |
| cycling_impact | TEXT | yes | Pipeline-classified impact | "High", "Medium", "Low", "Minimal" |
| cycling_summary | TEXT | yes | Claude-generated plain-English summary (high/medium only) | "Road closure on a busy cycle commute corridor..." |
| nearby_cycling_infra | TEXT | yes | Closest CID asset within 50m | "Cycleway 7 — Segregated cycle track (12m)" |
| activity_type | TEXT | yes | Type of activity (for non-permit works) | "Remedial works" |
| source_event | TEXT | yes | SNS event that triggered this update | "PERMIT_GRANTED", "WORK_START" |
| lon | DOUBLE PRECISION | yes | WGS84 longitude | -0.1148 |
| lat | DOUBLE PRECISION | yes | WGS84 latitude | 51.4613 |
| created_at | TIMESTAMPTZ | no | Row creation timestamp | auto |
| updated_at | TIMESTAMPTZ | no | Last modification timestamp | auto (trigger) |

### Indexes

- `idx_roadworks_borough` on `borough`
- `idx_roadworks_impact` on `cycling_impact`
- `idx_roadworks_status` on `work_status`

### Cycling Impact classification

| Level | Triggers |
|-------|----------|
| High | Road closure, lane closure, or near high-priority cycling infrastructure (cycleway route, segregated/stepped/partially-segregated track) |
| Medium | Signal-controlled works, convoy working, emergency works, or near medium-priority cycling infrastructure (mandatory lane, modal filter, contraflow) |
| Low | Give-and-take, some carriageway restriction |
| Minimal | Footway-only works with minimal carriageway impact |

### SNS event types processed

- `WORK_START`, `WORK_STOP`, `WORK_START_REVERTED`
- `PERMIT_SUBMITTED`, `PERMIT_GRANTED`, `PERMIT_REFUSED`, `PERMIT_CANCELLED`, `PERMIT_REVOKED`
- `PERMIT_ALTERATION_SUBMITTED`, `PERMIT_ALTERATION_GRANTED`
- `ACTIVITY_CREATED`, `ACTIVITY_UPDATED`, `ACTIVITY_CANCELLED`
- `SECTION_58_APPLIED`, `SECTION_58_REMOVED`

---

## 2. TfL Disruptions (`disruptions` table)

**Update cadence:** Daily poll at 09:00 UK time + on app startup
**Primary key:** `id` (auto-increment)
**Dedup key:** `disruption_id` (UNIQUE)
**Approximate volume:** ~70 active at any time across London (fewer in target boroughs)

### Columns

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| id | SERIAL | no | Auto-increment primary key | 1 |
| disruption_id | TEXT | no | TfL's unique disruption ID | "TIMS-225683" |
| name | TEXT | yes | Location and category | "Westminster Bridge Road — Works" |
| borough | TEXT | no | Geo-filtered borough | "Southwark" |
| category | TEXT | yes | Type of disruption | "Works", "Collisions", "Hazards", "Planned events" |
| sub_category | TEXT | yes | More specific category | "Roadworks" |
| status | TEXT | yes | Current state | "Active", "Scheduled", "Resolved" |
| severity | TEXT | yes | TfL severity level | "Serious", "Moderate", "Minimal" |
| location_desc | TEXT | yes | Human-readable location | "Westminster Bridge Road both directions" |
| corridors | TEXT | yes | Affected TfL corridors (comma-separated) | "TLRN Road Network" |
| start_time | TIMESTAMPTZ | yes | When disruption starts/started | 2026-03-10T08:00:00Z |
| end_time | TIMESTAMPTZ | yes | When disruption ends/ended | 2026-03-14T18:00:00Z |
| description | TEXT | yes | TfL's description (max 2000 chars) | "Temporary traffic signals..." |
| cycling_impact | TEXT | yes | Pipeline-classified impact | "High", "Medium", "Low", "Minimal" |
| cycling_summary | TEXT | yes | Claude-generated summary (high/medium only) | "Lane closure on key cycle commute route..." |
| nearby_cycling_infra | TEXT | yes | Closest CID asset within 50m | "Mandatory cycle lane (23m)" |
| lon | DOUBLE PRECISION | yes | WGS84 longitude | -0.1065 |
| lat | DOUBLE PRECISION | yes | WGS84 latitude | 51.4982 |
| created_at | TIMESTAMPTZ | no | Row creation timestamp | auto |
| updated_at | TIMESTAMPTZ | no | Last modification timestamp | auto (trigger) |

### Indexes

- `idx_disruptions_borough` on `borough`
- `idx_disruptions_status` on `status`

### Lifecycle

Disruptions that disappear from the TfL API are automatically marked as **Resolved**. The poller compares active IDs from the API against existing records and updates missing ones.

---

## 3. Cycling Collisions (`collisions` table)

**Update cadence:** One-off import via backfill script (DfT publishes yearly)
**Primary key:** `id` (auto-increment)
**Dedup key:** `collision_reference` (UNIQUE)
**Data source:** DfT STATS19 open data (collisions, casualties, vehicles CSVs)
**Current data range:** 2020-2024 (with option to backfill to 2010 or earlier)

### Columns

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| id | SERIAL | no | Auto-increment primary key | 1 |
| collision_reference | TEXT | no | STATS19 collision index | "2023010012345" |
| name | TEXT | yes | Road and date | "A23 — 15/06/2023" |
| borough | TEXT | no | Geo-filtered borough | "Croydon" |
| date | DATE | yes | Date of collision | 2023-07-15 |
| time | TEXT | yes | Time of collision | "08:30" |
| severity | TEXT | yes | Overall collision severity | "Fatal", "Serious", "Slight" |
| number_of_cyclists_hurt | INTEGER | no | Count of cyclist casualties | 1 |
| worst_cyclist_severity | TEXT | yes | Worst outcome for any cyclist | "Fatal", "Serious", "Slight" |
| other_vehicles | TEXT | yes | Non-cycle vehicles involved (comma-separated) | "Car, HGV" |
| road_name | TEXT | yes | Road name | "A23" |
| speed_limit | INTEGER | yes | Speed limit at location (mph) | 30 |
| junction_detail | TEXT | yes | Junction type | "T or staggered junction", "Crossroads" |
| light_conditions | TEXT | yes | Lighting at time of collision | "Daylight", "Darkness - lights lit" |
| weather | TEXT | yes | Weather conditions | "Fine no high winds", "Raining no high winds" |
| road_surface | TEXT | yes | Surface condition | "Dry", "Wet or damp" |
| data_year | TEXT | yes | Year of STATS19 dataset | "2023" |
| lon | DOUBLE PRECISION | yes | WGS84 longitude | -0.0876 |
| lat | DOUBLE PRECISION | yes | WGS84 latitude | 51.3721 |
| created_at | TIMESTAMPTZ | no | Row creation timestamp | auto |

### Indexes

- `idx_collisions_borough` on `borough`
- `idx_collisions_severity` on `severity`
- `idx_collisions_date` on `date`

### Notes

- Only collisions involving at least one **pedal cyclist casualty** are imported
- Vehicle type "Pedal cycle" is excluded from the "Other Vehicles" field (it's implicit)
- No `updated_at` — collision data is historical and doesn't change after import

---

## 4. Traffic Orders (`traffic_orders` table)

**Update cadence:** Daily poll at 09:30 UK time + on app startup
**Primary key:** `id` (auto-increment)
**Dedup key:** `dtro_id` (UNIQUE)
**Data source:** DfT D-TRO API (https://dtro.dft.gov.uk/v1)

### Columns

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| id | SERIAL | no | Auto-increment primary key | 1 |
| dtro_id | TEXT | no | DfT unique identifier | "d268d055-66c1-40cd-ab07-31237c6974d1" |
| name | TEXT | yes | TRO name | "Lambeth (Brixton Road) (No. 1) Traffic Order 2026" |
| dtro_reference | TEXT | yes | Local authority reference | "2026/TRO/0042" |
| borough | TEXT | no | Mapped from SWA code | "Lambeth" |
| regulation_type | TEXT[] | yes | What the order regulates (array) | {"cycleLane","miscRoadClosure"} |
| location_description | TEXT | yes | Where it applies | "Brixton Road from junction with..." |
| street_name | TEXT | yes | Affected streets (comma-separated) | "Brixton Road, Acre Lane" |
| made_date | DATE | yes | When order was made | 2026-03-01 |
| effective_date | DATE | yes | When order comes into force | 2026-03-15 |
| end_date | DATE | yes | Expiry (if temporary) | 2026-06-15 |
| authority | TEXT | yes | Traffic regulation authority | "London Borough of Lambeth" |
| action_type | TEXT | yes | What's happening | "New", "Revocation" |
| cycling_impact | TEXT | yes | Pipeline-classified impact | "Positive", "Negative", "Neutral", "Needs Review" |
| cycling_summary | TEXT | yes | Claude-generated summary (Negative/Needs Review only) | "Revocation of existing cycle lane on..." |
| nearby_cycling_infra | TEXT | yes | Closest CID asset within 50m | "Advisory cycle lane (8m)" |
| schema_version | TEXT | yes | D-TRO schema version | "3.3.1" |
| lon | DOUBLE PRECISION | yes | WGS84 longitude | -0.1148 |
| lat | DOUBLE PRECISION | yes | WGS84 latitude | 51.4613 |
| created_at | TIMESTAMPTZ | no | Row creation timestamp | auto |
| updated_at | TIMESTAMPTZ | no | Last modification timestamp | auto (trigger) |

### Indexes

- `idx_traffic_orders_borough` on `borough`
- `idx_traffic_orders_impact` on `cycling_impact`

### Cycling Impact classification (different scale from roadworks)

| Level | Triggers |
|-------|----------|
| Positive | Contains `cycleLane` regulation type (new cycle infrastructure) |
| Negative | Road closures, cycle lane closures, one-way orders, or revocation of positive regulations |
| Neutral | Parking-only restrictions (no-waiting, permit parking, disabled bays, taxi ranks) |
| Needs Review | Mixed regulations, speed limits, bus lanes, loading restrictions, or Neutral orders near cycling infrastructure |

### Regulation type values

**Positive:** `cycleLane`
**Negative:** `miscRoadClosure`, `miscCycleLaneClosure`, `miscOneWay`
**Neutral:** `kerbsideNoWaiting`, `kerbsideParkingPlace`, `kerbsidePermitParkingPlace`, `kerbsideDisabledBadgeHoldersOnly`, `kerbsideTaxiRank`
**Needs Review:** `miscSuspensionOfParkingRestriction`, `speedLimit`, `miscBusLane`, `kerbsideLoadingPlace`

---

## 5. Cycling Infrastructure Reference Layer (runtime only)

This is a **spatial index loaded at app startup**, not stored in the database. It enriches the other tables via the `nearby_cycling_infra` field.

**Source data:**
- TfL Cycling Infrastructure Database (CID): cycle lanes/tracks from `cycling.data.tfl.gov.uk`
- TfL Cycleway Routes: named routes (C1, C5, C7, etc.) from ArcGIS FeatureServer
- Restricted Routes: modal filters, contraflows from CID

**Total features:** ~6,719 (pre-filtered to target boroughs)
**Search radius:** 50 metres from work/disruption/order coordinates

### Asset types (in priority order)

| Priority | Asset Type | Source | Description |
|----------|-----------|--------|-------------|
| 1 (highest) | cycleway_route | ArcGIS | Named TfL Cycleway (e.g., "Cycleway 7") |
| 2 | segregated_cycleway | CID | Physically separated cycle track |
| 3 | stepped_cycleway | CID | Stepped (kerb-level) cycle track |
| 4 | partially_segregated_cycleway | CID | Partially separated cycle track |
| 5 | mandatory_lane | CID | White-line mandatory cycle lane |
| 6 | modal_filter | CID restricted routes | Bollard/planter blocking motor traffic |
| 7 | contraflow_lane | CID | Contraflow cycle lane |
| 8 | advisory_lane | CID | Dashed-line advisory cycle lane |
| 9 (lowest) | shared_use_path | CID | Shared pedestrian/cycle path |

### Impact upgrade rules

When a roadwork/disruption is within 50m of cycling infrastructure:
- **Near cycleway_route, segregated, stepped, or partially_segregated** -> impact upgraded to **High**
- **Near mandatory, modal_filter, contraflow, or advisory** -> impact upgraded to **Medium**
- **Near shared_use_path** -> no upgrade
- Upgrades are **one-way only** — CID proximity never downgrades an existing impact

---

## 6. Coordinates

All coordinate columns use **WGS84** (EPSG:4326) stored as separate `lon` and `lat` DOUBLE PRECISION columns.

- `lon` = longitude (e.g., -0.1148 = 0.1148 degrees West)
- `lat` = latitude (e.g., 51.4613 = 51.4613 degrees North)

Street Manager data arrives in **British National Grid (EPSG:27700)** and is converted to WGS84 by the pipeline using pyproj. TfL and STATS19 data is already in WGS84.

### Querying by bounding box

```sql
SELECT * FROM roadworks
WHERE lon BETWEEN -0.15 AND -0.05
  AND lat BETWEEN 51.45 AND 51.50;
```

---

## 7. Example Queries

### Active high-impact roadworks

```sql
SELECT name, street_name, borough, cycling_impact, cycling_summary,
       proposed_start, proposed_end, lon, lat
FROM roadworks
WHERE cycling_impact IN ('High', 'Medium')
  AND work_status IN ('Planned', 'In progress')
ORDER BY proposed_start;
```

### Collision hotspots by road

```sql
SELECT road_name, borough, COUNT(*) as total,
       SUM(CASE WHEN severity = 'Fatal' THEN 1 ELSE 0 END) as fatal,
       SUM(CASE WHEN severity = 'Serious' THEN 1 ELSE 0 END) as serious
FROM collisions
GROUP BY road_name, borough
ORDER BY total DESC
LIMIT 20;
```

### All data near a point (e.g., within ~500m of Brixton)

```sql
-- Rough bounding box (~500m at London's latitude)
SELECT 'roadwork' as type, name, cycling_impact, lon, lat FROM roadworks
WHERE lon BETWEEN -0.120 AND -0.110 AND lat BETWEEN 51.457 AND 51.466
UNION ALL
SELECT 'collision', name, severity, lon, lat FROM collisions
WHERE lon BETWEEN -0.120 AND -0.110 AND lat BETWEEN 51.457 AND 51.466
UNION ALL
SELECT 'disruption', name, cycling_impact, lon, lat FROM disruptions
WHERE lon BETWEEN -0.120 AND -0.110 AND lat BETWEEN 51.457 AND 51.466;
```

### Traffic orders affecting cycling

```sql
SELECT name, borough, regulation_type, cycling_impact, cycling_summary,
       effective_date, end_date
FROM traffic_orders
WHERE cycling_impact IN ('Positive', 'Negative', 'Needs Review')
ORDER BY effective_date DESC;
```

---

## 8. Data Freshness & Pipeline Schedule

| Table | Update Mechanism | Frequency | Typical Latency |
|-------|-----------------|-----------|-----------------|
| roadworks | SNS webhook (push) | Real-time | Seconds after DfT publishes |
| disruptions | HTTP poll | Daily at 09:00 UK + startup | Up to 24 hours |
| collisions | Manual import script | Annual | Months (DfT publishes ~6 months after year end) |
| traffic_orders | HTTP poll | Daily at 09:30 UK + startup | Up to 24 hours |

---

## 9. Other Data Sources (not in this database)

The LCC South London Notion workspace contains manually curated tables that may be relevant for a visualisation project:

- **Ward councillor research** — political data for the May 2026 local elections
- Other campaign tables maintained by borough group volunteers

These are accessed via the Notion API (separate from this PostgreSQL database).
