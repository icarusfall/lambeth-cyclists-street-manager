# South London Street Works Monitor

## Architecture & Implementation Specification

**Project:** LCC South London Street Works Monitor
**Author:** Charlie (Lambeth Cyclists / London Cycling Campaign)
**Date:** March 2026
**Purpose:** Hand-off document for Claude Code implementation
**Repository:** https://github.com/icarusfall/lambeth-cyclists-street-manager

---

## Implementation Progress

| Phase | Component | Status |
|-------|-----------|--------|
| 1 | Project setup (pyproject.toml, Dockerfile, config) | DONE |
| 1 | Borough boundary loader | DONE |
| 1 | SNS webhook receiver | DONE |
| 1 | SNS signature verification | DONE |
| 1 | Geo-filter pipeline | DONE |
| 1 | Deduplication (PostgreSQL ON CONFLICT upserts) | DONE |
| 1 | Database writer (PostgreSQL + PostGIS via asyncpg) | DONE |
| 1 | Cycling impact classifier (rule-based) | DONE |
| 1 | Claude API enrichment (optional, for high/medium) | DONE |
| 1 | Deployment to Railway | DONE |
| 1 | Street Manager open data registration | DONE — all three topics confirmed (activity, section-58, permit) |
| 1 | Roadworks table (PostgreSQL) | DONE |
| 1–5 | Tests (128 passing) | DONE |
| 2 | TfL Live Disruptions API integration | DONE |
| 2 | Disruptions table (PostgreSQL) | DONE |
| 3 | STATS19 cycling collision data import | DONE |
| 3 | Collisions table (PostgreSQL) | DONE |
| 4 | D-TRO integration | DONE |
| 4 | Traffic Orders table (PostgreSQL) | DONE |
| 5 | TfL Cycling Infrastructure Database (CID) reference layer | DONE |
| 5 | Classifier upgrade: CID-aware route importance scoring | DONE |
| 5 | TfL Cycleway routes (named routes like Cycleway 5, 7, etc.) | DONE |
| 5 | "Nearby Cycling Infrastructure" database field (all 3 tables) | DONE |
| — | Notion → PostgreSQL + PostGIS migration | DONE |
| — | Data Dictionary (DATA_DICTIONARY.md) | DONE |
| — | LAQN air quality data integration | DONE |
| — | Air Quality table (PostgreSQL) | DONE |
| — | Fix TfL disruption datetime parsing (ISO strings → datetime objects) | DONE |
| — | Reduce log noise (webhook DEBUG, disable uvicorn access log) | DONE |
| 6 | Planning London Datahub integration | PARKED — revisit with Postgres in place |
| 6 | Development Activity database | PARKED |
| 7 | USRN enrichment, historical analysis, alerts, dashboard, agenda integration | DEFERRED — dashboard/visualisation split to separate project |

### Changes from Original Spec

1. **SNS-only architecture (not polling).** The Street Manager open data feed is SNS-only — there is no public REST API or CSV export for open data consumers. The REST API (`GET /works/updates`) requires an authenticated organizational account (highway authority/utility company). Railway provides the HTTPS endpoint for SNS; no AWS account is needed.

2. **No `schedule`/`apscheduler` needed.** Since we're using SNS push (not polling), there are no scheduled jobs in Phase 1. The app is purely event-driven. Scheduled jobs will be added in Phase 2 for D-TRO polling.

3. **Deduplication via Notion, not local JSON file.** Railway containers can restart and lose local state. Instead, the app queries Notion by `permit_reference_number` to check for existing records before creating new ones. An in-memory cache (warmed at startup from Notion) avoids per-item Notion queries during normal operation.

4. **`notion-client` pinned to v2.2.1.** Version 2.3+ removed `databases.query()`. Pinned to match the version used by the lambeth-cyclists-claude project.

5. **`pydantic-settings` target_boroughs is a string, not a list.** Pydantic-settings v2 tries to JSON-parse `list[str]` fields from env vars, which fails for comma-separated strings. Changed to a `str` field with a `get_target_boroughs()` method that splits on commas.

6. **SNS signature verification added.** The original spec noted this was missing. Now implemented using the `cryptography` package to validate SNS message signatures against AWS signing certificates.

7. **SWA codes corrected.** The original spec's Section 10 SWA codes were wrong (e.g. 5210=Camden not Croydon, 5540=Hounslow not Lambeth). All codes verified against the official GeoPlace SWA_ORG_ACTIVE registry in March 2026 and corrected in `src/config.py`. See Section 10 for the corrected table.

8. **Borough boundaries sourced from ONS, not London Datastore.** The London Datastore provides shapefiles, not GeoJSON. Used the ONS Open Geography Portal ArcGIS API instead (`Local_Authority_Districts_December_2024_Boundaries_UK_BFE`), which provides GeoJSON directly. Property key for borough names is `LAD24NM`.

9. **Removed planned files that weren't needed.** `parser.py`, `poller.py`, `state/dedup.py`, `dtro/client.py`, and `scripts/backfill.py` from the original structure were not created — the SNS architecture is simpler and doesn't need them. Added `pipeline.py` and `sns_verify.py` instead.

10. **TfL disruption categories differ from spec.** The architecture doc assumed categories like `PlannedWork`, `RoadClosure`, `SpecialEvent`, `Incident`. The live API actually returns: `Works`, `Collisions`, `Hazards`, `Network delays`, `Asset issues`, `Breakdowns`, `Planned events`. Classifier and schema updated to match real data. Severities are: `Serious`, `Moderate`, `Minimal`.

11. **TfL polling daily at 09:00, not every 5 minutes.** The original spec called for 5-minute polling. Changed to daily at 09:00 UK time (with an initial poll on startup) since disruption data doesn't change fast enough to justify 288 API calls per day. Uses `asyncio.sleep` to wait until the next 09:00 — no `apscheduler` dependency needed.

12. **No `apscheduler` dependency.** The TfL poller uses a simple `asyncio` task with sleep-until-target-time logic instead of adding a scheduler dependency. This keeps the dependency footprint small and avoids configuration complexity.

13. **Activity events have a different payload shape than permits.** The `prod-activity-topic` sends events with different field names (e.g. `activity_reference_number` not `permit_reference_number`, `activity_coordinates` not `works_location_coordinates`, `start_date`/`end_date` not `proposed_start_date`/`proposed_end_date`). A normalisation layer in `src/pipeline.py` (`_normalise_activity_data()`) maps activity fields to permit equivalents before the rest of the pipeline runs. Activity coordinates can be LINESTRING (not just POINT); the geo-filter extracts the midpoint for polygon containment checks.

14. **SNS subscription status.** All three topics confirmed: `prod-activity-topic` and `prod-section-58-topic` subscribed on 10 March 2026; `prod-permit-topic` re-registered and confirmed week of 14 March 2026 (permit events visible in Railway logs from 14:55 UTC on 14 March 2026).

15. **STATS19 uses stdlib `csv`, not pandas.** The original spec called for pandas to parse STATS19 CSVs. Used stdlib `csv.DictReader` instead — the data is simple enough that pandas would be unnecessary overhead, and it keeps the dependency footprint small. All coded integer values are mapped to human-readable labels via lookup dicts in the importer module.

16. **D-TRO API URL differs from spec.** The spec referenced `d-tro.dft.gov.uk` but the actual production portal is `dltro-ui.gov.uk` and the API is at `dtro.dft.gov.uk/v1`. Auth uses API Key + API Secret (not App ID) as OAuth2 client credentials. Max page size is 50, not 100.

17. **D-TRO Regulation Type is multi-select, not select.** Real D-TRO data shows orders with multiple regulation types (e.g. `kerbsideNoWaiting` + `kerbsideParkingPlace` + `kerbsideTaxiRank`). Changed from select to multi-select in Notion schema. Added D-TRO ID (UUID) for dedup, Action Type, Made Date, and Schema Version fields.

18. **D-TRO coordinates use SRID-prefixed BNG linestrings.** Format is `SRID=27700;LINESTRING (...)` — the existing `parse_bng_wkt_to_wgs84()` handles this correctly since it searches for "LINESTRING" in the string and extracts coordinate pairs.

19. **STATS19 dates need DD/MM/YYYY → ISO conversion.** The `_date()` helper was written for Street Manager ISO dates. STATS19 uses `DD/MM/YYYY` format, so a `_parse_stats19_date()` converter was added in `collision_to_notion_properties()`.

---

## 1. Project Overview

### What This Does

A Python daemon that monitors roadworks and traffic regulation orders across south London, filters for cycling-relevant activity, and populates Notion databases that can be shared with LCC borough groups (Lambeth Cyclists, Southwark Cyclists, Wandsworth Cyclists, etc.).

### Why It Matters

Roadworks and traffic orders directly affect cycling routes — road closures, lane restrictions, new speed limits, parking changes, and temporary traffic management all change conditions for people on bikes. Currently, no LCC borough group has systematic visibility of this. This tool gives south London cycling groups early, structured notice of works affecting their areas, and builds a historical dataset for advocacy (e.g. identifying roads most disrupted by works, as demonstrated by Chris Carlon's analysis of Street Manager data).

### Who It Serves

The system covers multiple London boroughs. Each LCC borough group can see a filtered view of their area in Notion. The initial borough set:

- **Core:** Lambeth, Southwark, Wandsworth, Lewisham
- **Extended:** Merton, Croydon
- **Bridge crossings:** City of London, Westminster

This list is configurable via environment variable.

---

## 2. Data Sources

### 2.1 Street Manager (DfT) — Roadworks & Street Works

**What:** Every utility street work and highway authority road work in England.

**API type:** AWS SNS push notifications. This is the **only** open data access method — there is no public REST polling API or CSV export for open data consumers.

**Registration:** Free open data account at https://www.manage-roadworks.service.gov.uk/open-data-onboarding

**Status:** Registration submitted 8 March 2026. Two of three topics confirmed (activity + section-58). The permit topic subscription failed due to a malformed endpoint URL and needs re-registration (ticket raised with Street Manager helpdesk). The endpoint is `https://lambeth-cyclists-street-manager-production.up.railway.app/webhook/street-manager`.

**Support helpdesk:** https://streetmanager.atlassian.net/servicedesk/customer/portals

**Three SNS topics to subscribe to:**
- `arn:aws:sns:eu-west-2:287813576808:prod-permit-topic` — permits (the main one)
- `arn:aws:sns:eu-west-2:287813576808:prod-activity-topic` — highway authority activities
- `arn:aws:sns:eu-west-2:287813576808:prod-section-58-topic` — Section 58 restrictions

**Notification payload (permit example):**

```json
{
  "event_reference": 678,
  "event_type": "WORK_START",
  "object_data": {
    "work_reference_number": "0000218889274",
    "permit_reference_number": "0000218889274-01",
    "promoter_swa_code": "STPR",
    "promoter_organisation": "Smoke Test Promoter",
    "highway_authority": "CITY OF WESTMINSTER",
    "works_location_coordinates": "POINT(527155.33 182227.95)",
    "street_name": "CHURCH STREET",
    "area_name": "CHURCH STREET",
    "work_category": "Minor",
    "traffic_management_type": "Road closure",
    "proposed_start_date": "2020-06-23T23:00:00.000Z",
    "proposed_end_date": "2020-06-27T23:00:00.000Z",
    "actual_start_date_time": "2020-06-24T10:11:00.000Z",
    "work_status": "Works in progress",
    "usrn": "8400794",
    "highway_authority_swa_code": "5990",
    "work_category_ref": "minor",
    "traffic_management_type_ref": "road_closure",
    "work_status_ref": "in_progress",
    "activity_type": "Utility repair and maintenance works",
    "is_ttro_required": "Yes",
    "works_location_type": "Footway"
  },
  "event_time": "2020-06-24T10:11:00.000Z",
  "object_type": "PERMIT",
  "object_reference": "0000218889274-01",
  "version": 1
}
```

**Key fields for our purposes:**
- `works_location_coordinates` — WKT POINT in British National Grid (EPSG:27700), needs conversion to WGS84 for geo-filtering
- `highway_authority_swa_code` — identifies who manages the road (borough council or TfL)
- `traffic_management_type_ref` — road_closure, lane_closure, multi_way_signals, two_way_signals, convoy_working, etc.
- `work_category_ref` — major, standard, minor, immediate_urgent, immediate_emergency
- `work_status_ref` — planned, in_progress, completed, cancelled, etc.
- `street_name`, `area_name`, `usrn` — location identifiers

**Important:** TfL manages the TLRN (red routes) and will appear as the highway authority for major roads passing through our target boroughs (e.g. A23 Brixton Road, A3 Kennington Road, A202). We CANNOT rely solely on `highway_authority_swa_code` matching a borough — we must also geo-filter works from other authorities (primarily TfL) that fall within our target area.

**Event types we process:**
- `WORK_START`, `WORK_STOP`, `WORK_START_REVERTED`
- `PERMIT_SUBMITTED`, `PERMIT_GRANTED`, `PERMIT_REFUSED`, `PERMIT_CANCELLED`, `PERMIT_REVOKED`
- `PERMIT_ALTERATION_SUBMITTED`, `PERMIT_ALTERATION_GRANTED`
- `ACTIVITY_CREATED`, `ACTIVITY_UPDATED`, `ACTIVITY_CANCELLED`
- `SECTION_58_APPLIED`, `SECTION_58_REMOVED`
- All other event types (inspections, FPNs, comments, reinstatements) are silently acknowledged and discarded.

**API documentation:** https://department-for-transport-streetmanager.github.io/street-manager-docs/api-documentation/

### 2.2 D-TRO Service (DfT) — Digital Traffic Regulation Orders (Phase 2)

**What:** Machine-readable versions of traffic regulation orders — speed limits, parking restrictions, one-way streets, road closures, weight limits, etc.

**API type:** REST API at https://dltro-ui.gov.uk

**Registration:** Free at the URL above. App credentials obtained 12 March 2026.

**Status:** Beta. API credentials obtained 12 March 2026. Data availability explored: Lambeth has 112 D-TROs (road closures, licenses), Lewisham 1 (parking consolidation), Croydon 3 (road closures). Southwark, Wandsworth, Merton, City of London, Westminster not yet publishing. TfL search returns 500 (their issue).

**GitHub:** https://github.com/department-for-transport-public/D-TRO — contains data model docs, schema files, and example data for the current spec version (3.5.0).

### 2.3 Borough Boundary Data — Geographic Filtering

**What:** GeoJSON polygon boundaries for London boroughs, used to determine whether a roadwork/order falls within our target area.

**Source used:** ONS Open Geography Portal ArcGIS REST API — `Local_Authority_Districts_December_2024_Boundaries_UK_BFE` dataset. Downloaded as GeoJSON directly via API query, stored in repo as `data/london_boroughs.geojson`. Property key for borough names: `LAD24NM`.

**Why ONS and not London Datastore:** The London Datastore provides shapefiles (requiring conversion), while the ONS portal serves GeoJSON directly via its ArcGIS API.

**Coordinate systems:** Street Manager uses British National Grid (EPSG:27700). Borough boundaries are in WGS84 (EPSG:4326). Incoming BNG coordinates are converted to WGS84 using `pyproj` at processing time.

### 2.4 TfL Live Traffic Disruptions API (Phase 2)

**What:** Real-time feed of traffic disruptions monitored by TfL's 24/7 traffic control centre — accidents, incidents, roadworks, public events, protests, filming, emergency road closures. This catches disruptions that Street Manager does not cover (unplanned incidents, events, TfL-monitored roadworks reported separately).

**API type:** REST API (TfL Unified API). JSON responses. Polls daily at 09:00 UK time.

**Endpoint:** `https://api.tfl.gov.uk/Road/all/Disruption` (with optional `?app_key={KEY}`)

**Registration:** Free API key at https://api-portal.tfl.gov.uk/ — gives 500 requests/minute. Works without a key at lower rate limits.

**Status:** DONE. Polling daily at 09:00 UK time (+ on startup). Live-tested: ~35 disruptions in target boroughs from ~99 total.

**Data format:** Each disruption includes:
- `id` — unique disruption ID (e.g. "TIMS-225540")
- `category` — observed values: "Works", "Collisions", "Hazards", "Network delays", "Asset issues", "Breakdowns", "Planned events"
- `subCategory` — more specific cause
- `status` — observed: "Active" (resolved disruptions drop off the feed)
- `severity` — observed: "Serious", "Moderate", "Minimal"
- `location` — text description (e.g. "[A23] STREATHAM HILL (SW16 ,SW2 ) (Lambeth)")
- `geography` — GeoJSON geometry (Point or LineString) in WGS84
- `corridors` — affected road corridors (array of objects with `name`)
- `startDateTime`, `endDateTime` — timing
- `comments` — free-text description of the disruption

**Geo-filtering:** The `geography` field provides WGS84 coordinates, so the existing borough polygon containment check works directly (no BNG conversion needed). For LineString geometries, the centroid is used.

**Why this is valuable:** Street Manager covers planned utility/highway works. TfL Disruptions covers everything else — burst water mains, traffic collisions, protests, marathon routes, filming, emergency bridge closures. Together they give near-complete coverage of anything disrupting cycling in south London.

**Implementation:** An asyncio background task polls the TfL API daily at 09:00 UK time (with an initial poll on startup). Results are geo-filtered against borough polygons, classified for cycling impact, and upserted to the Notion Disruptions database. Dedup on TfL disruption `id`. When a disruption disappears from the feed, it is marked as "Resolved" in Notion.

### 2.5 STATS19 Road Collision Data (Phase 3)

**What:** Every road traffic collision in Great Britain reported to the police, including detailed information on casualties, vehicles involved, location, severity, and contributing factors. Published by the DfT as open data CSV files.

**Data source:** https://www.gov.uk/government/statistical-data-sets/road-safety-open-data

**Update frequency:** Annual final data published in late September. Provisional mid-year data (January–June) published in late November. Data for 2024 is available now; provisional H1 2025 data published November 2025.

**Data files (CSV):**
- Collisions — one row per collision, with coordinates (WGS84), date/time, severity, road type, speed limit, junction detail, weather, light conditions
- Casualties — one row per person hurt/killed, with severity, age, sex, road user type (pedal cyclist = vehicle type 1), casualty class
- Vehicles — one row per vehicle involved, with vehicle type, manoeuvre, driver age/sex, journey purpose

**Filtering strategy:**
1. Download the collisions CSV, filter to coordinates within the target borough polygons (same geo-filter reused)
2. Join to casualties CSV, filter to `casualty_type = "Pedal Cyclist"` (or `vehicle_type = 1` in the vehicles table)
3. This gives you every collision involving a cyclist in the target boroughs

**Why this is valuable:** Collision data is the most powerful tool for cycling advocacy. It lets you show exactly where cyclists are being hurt, which junctions are dangerous, what vehicle types are involved, and how patterns change over time. Cross-referencing collision locations with active roadworks could also reveal whether roadworks are creating temporary danger spots.

**Implementation:** A scheduled job that runs when new data is published (check quarterly). Downloads CSVs, filters, and populates a Cycling Collisions Notion database. Could also be run as a one-off backfill script for historical data.

**Related tools:** The `stats19` R package (https://itsleeds.github.io/stats19/) provides helper functions for downloading and parsing this data, though a Python implementation is straightforward since the files are just CSVs.

### 2.6 TfL Cycling Infrastructure Database — CID (Phase 5)

**What:** Every piece of cycling infrastructure in London — 240,000 assets including cycle lanes/tracks (segregated and painted), cycle parking, modal filters, traffic calming, advanced stop lines, crossings, wayfinding signs, and restricted points. Surveyed street-by-street across all London boroughs.

**Data source:** https://cycling.data.tfl.gov.uk/ (under CycleInfrastructure/) — JSON files per asset type. Also available via TfL Unified API `/Place` endpoint for cycle parking.

**Schema documentation:** Available at the same URL under CycleInfrastructure/Documentation.

**Update frequency:** Periodically updated by TfL as infrastructure changes. The original survey was 2017–18; updates have been made since.

**How we use it:** NOT as a live feed — as a **static reference layer** loaded at startup alongside the borough boundaries. Used to enrich the cycling impact classifier:
- Roadwork on a road with a segregated cycleway → automatically "high" impact (the cycleway is probably affected)
- Roadwork near a modal filter → flag for review (filter may be temporarily removed)
- Roadwork on a road with no cycling infrastructure → lower default impact
- Cross-reference with cycle route data (also from TfL) to flag works on Cycleways

**Implementation:** Download the CID JSON files, load cycle lanes/tracks and restricted routes as a GeoDataFrame or Shapely geometry collection. For each incoming roadwork, check proximity to CID assets (buffer check, e.g. within 50m of a cycle lane). Add a "Affects Cycle Infrastructure" field to the Roadworks Notion database and use it to upgrade the cycling impact classification.

### 2.7 Planning London Datahub — GLA (Phase 6)

**What:** Real-time planning application data from all London boroughs, updated daily. Covers applications, permissions, commencements, and completions. Published by the GLA.

**API type:** REST API with structured JSON responses.

**Documentation:** https://www.london.gov.uk/programmes-strategies/planning/digital-planning/planning-london-datahub — includes API connection technical document and schema.

**Registration:** Publicly accessible.

**Why this matters for cycling:** Major developments generate:
- Construction traffic (HGVs on cycling routes)
- Temporary road closures and diversions (often for years on large sites)
- S278 highway works (developer-funded changes to roads, which should include cycling improvements)
- S106 obligations (which may include cycling infrastructure funding)
- New trip generation that changes traffic patterns on local roads

**Filtering strategy:** Query for applications in the target boroughs, filter to major applications (likely to have transport impact). Use Claude to assess cycling relevance from the application description.

**Implementation:** A daily scheduled poll. Write to a new Development Activity Notion database. Lower priority than other phases because the data is less directly actionable — it's strategic intelligence rather than immediate operational awareness.

**Note:** Lambeth is a pioneer in the Open Digital Planning programme, so data quality for Lambeth should be good. Southwark is also a partner.

---

## 3. Architecture

### 3.1 High-Level Design

```
                    ┌─────────────────────┐
                    │   Street Manager    │
                    │   AWS SNS Topics    │
                    └────────┬────────────┘
                             │ HTTPS POST (signed)
                             ▼
┌──────────────────────────────────────────────────────┐
│            Python Daemon (Railway)                    │
│  lambeth-cyclists-street-manager-production           │
│  .up.railway.app                                     │
│                                                      │
│  ┌─────────────┐  ┌───────────────────────────────┐  │
│  │ FastAPI      │  │  Scheduled Jobs (Phase 2+)    │  │
│  │ webhook      │  │  - TfL Disruptions (09:00)    │  │
│  │ receiver     │  │  - D-TRO poll (09:30)         │  │
│  │ + SNS sig    │  │  - STATS19 import (quarterly) │  │
│  │   verify     │  │  - Planning Datahub (daily)   │  │
│  └──────┬───────┘  └──────────┬────────────────────┘  │
│         │                     │                       │
│         ▼                     ▼                       │
│  ┌──────────────────────────────────────────────┐     │
│  │        Geo-Filter Engine                     │     │
│  │  1. SWA code check (fast path)               │     │
│  │  2. BNG→WGS84 + point-in-polygon             │     │
│  │  Borough boundaries loaded at start           │     │
│  └──────────────┬───────────────────────────────┘     │
│                 │                                      │
│                 ▼                                      │
│  ┌──────────────────────────────────────────────┐     │
│  │     Cycling Impact Classifier                │     │
│  │  - Rule-based (all works)                    │     │
│  │  - Claude Haiku summary (high/med)           │     │
│  │  - CID proximity check (Phase 5)             │     │
│  └──────────────┬───────────────────────────────┘     │
│                 │                                      │
│                 ▼                                      │
│  ┌──────────────────────────────────────────────┐     │
│  │     Notion Writer                            │     │
│  │  - Upsert to Roadworks DB                    │     │
│  │  - Upsert to Disruptions DB (Phase 2)        │     │
│  │  - Upsert to Collisions DB (Phase 3)         │     │
│  │  - Upsert to Traffic Orders DB (Phase 4)     │     │
│  │  - Upsert to Development DB (Phase 6)        │     │
│  │  - Dedup via source-specific reference key    │     │
│  │  - In-memory cache warmed at start            │     │
│  └──────────────────────────────────────────────┘     │
│                                                      │
│  Reference Data (loaded at startup):                  │
│  - Borough boundary polygons (ONS GeoJSON)            │
│  - TfL CID cycle infrastructure (Phase 5)             │
│                                                      │
└──────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────────────┐
                    │   Notion Workspace      │
                    │   (Lambeth Cyclists)     │
                    │                         │
                    │  ┌───────────────────┐  │
                    │  │ Roadworks DB      │  │ ← DONE
                    │  └───────────────────┘  │
                    │  ┌───────────────────┐  │
                    │  │ Disruptions DB    │  │ ← Phase 2
                    │  └───────────────────┘  │
                    │  ┌───────────────────┐  │
                    │  │ Cycling           │  │ ← Phase 3
                    │  │ Collisions DB     │  │
                    │  └───────────────────┘  │
                    │  ┌───────────────────┐  │
                    │  │ Traffic           │  │ ← Phase 4
                    │  │ Orders DB         │  │
                    │  └───────────────────┘  │
                    │  ┌───────────────────┐  │
                    │  │ Development       │  │ ← Phase 6
                    │  │ Activity DB       │  │
                    │  └───────────────────┘  │
                    └─────────────────────────┘
```

### 3.2 Deployment

- **Platform:** Railway (existing infrastructure from Lambeth Cyclists email automation)
- **URL:** `https://lambeth-cyclists-street-manager-production.up.railway.app`
- **Runtime:** Python 3.11 (Docker)
- **Process:** Single long-running process with a FastAPI web server for the SNS webhook
- **Database:** None — Notion is the datastore. Deduplication uses an in-memory cache (warmed from Notion at startup) backed by Notion queries for cache misses.
- **Health check:** `GET /health` — returns status, uptime, notification count, borough count

### 3.3 Configuration (Environment Variables)

```
# Borough list (comma-separated borough names matching the boundary GeoJSON)
# Optional — defaults to all 8 boroughs if not set
TARGET_BOROUGHS=Lambeth,Southwark,Wandsworth,Lewisham,Merton,Croydon,City of London,Westminster

# Notion (required)
NOTION_API_KEY=secret_xxx
NOTION_ROADWORKS_DB_ID=xxx

# Anthropic (optional — for Claude cycling impact summaries on high/medium works)
ANTHROPIC_API_KEY=sk-ant-xxx

# App
WEBHOOK_PATH=/webhook/street-manager
LOG_LEVEL=INFO

# Set automatically by Railway — do not set manually
# PORT=8080
```

**Removed from original spec:** `BOROUGH_SWA_CODES` (hardcoded in config.py), `STREET_MANAGER_API_EMAIL`/`PASSWORD` (not needed for SNS).

**Added in Phase 2:**
- `TFL_API_KEY` — optional, works without key at lower rate limits
- `NOTION_DISRUPTIONS_DB_ID` — required for TfL disruptions integration

**Future env vars (added in later phases):**
- Phase 3: `NOTION_COLLISIONS_DB_ID`
- Phase 4: `DTRO_API_KEY`, `NOTION_TRAFFIC_ORDERS_DB_ID`
- Phase 6: `NOTION_DEVELOPMENT_DB_ID`

---

## 4. Geo-Filtering Logic

### 4.1 Two-Tier Filter

Implemented in `src/geo/filter.py`:

```python
class GeoFilter:
    def check(self, object_data: dict) -> tuple[bool, str]:
        """Returns (should_include, borough_name)."""

        # Fast path: highway authority IS one of our target boroughs
        ha_swa = object_data.get("highway_authority_swa_code", "")
        if ha_swa in self._swa_to_borough:
            return True, self._swa_to_borough[ha_swa]

        # Geo path: for TfL roads, cross-boundary utility works, etc.
        # Activities use activity_coordinates; permits use works_location_coordinates
        coords_wkt = (
            object_data.get("works_location_coordinates")
            or object_data.get("activity_coordinates")
        )
        if not coords_wkt:
            return False, ""

        point = parse_bng_wkt_to_wgs84(coords_wkt)
        if point is None:
            return False, ""

        for borough_name, polygon in self._polygons.items():
            if polygon.contains(point):
                return True, borough_name

        return False, ""
```

### 4.2 Coordinate Conversion

Implemented in `src/geo/filter.py`. Supports both POINT and LINESTRING WKT geometries (LINESTRING uses midpoint for containment check). Tested with real coordinates — Brixton Road correctly resolves to Lambeth, Borough High Street to Southwark, etc.

### 4.3 Borough Boundary Loading

Implemented in `src/geo/boundaries.py`. Handles multiple GeoJSON property key naming conventions (`NAME`, `name`, `LAD24NM`, etc.) with case-insensitive matching.

---

## 5. Cycling Relevance Classifier

### 5.1 Rule-Based Pre-Filter

Implemented in `src/classifier/rules.py`, unchanged from spec.

### 5.2 Claude API Enrichment

Implemented in `src/classifier/claude.py`. Uses Claude Haiku (`claude-haiku-4-5-20251001`) for cost control. Only called for high/medium impact works. Returns `None` if `ANTHROPIC_API_KEY` is not configured — the feature is fully optional.

---

## 6. Notion Database Schemas

### 6.1 Roadworks Database — DONE

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Street name + area (auto-generated) |
| Permit Reference | Rich text | Street Manager permit reference number |
| Work Reference | Rich text | Street Manager work reference number |
| Borough | Select | Which target borough this falls in |
| Highway Authority | Rich text | The managing authority (e.g. "Lambeth", "Transport for London") |
| Street Name | Rich text | Street name from notification |
| Area | Rich text | Area name from notification |
| USRN | Rich text | Unique Street Reference Number |
| Promoter | Rich text | Organisation doing the work |
| Work Category | Select | Major / Standard / Minor / Immediate Urgent / Immediate Emergency |
| Traffic Management | Select | Road closure / Lane closure / Multi-way signals / Two-way signals / Give and take / Convoy / Some restriction / No restriction |
| Work Status | Select | Planned / In progress / Completed / Cancelled |
| Proposed Start | Date | Planned start date |
| Proposed End | Date | Planned end date |
| Actual Start | Date | When work actually started |
| Cycling Impact | Select | High / Medium / Low / Minimal |
| Cycling Summary | Rich text | Claude-generated summary (if applicable) |
| Activity Type | Rich text | e.g. "Utility repair and maintenance works" |
| TTRO Required | Checkbox | Whether a temporary traffic regulation order is required |
| Coordinates | Rich text | WGS84 lon,lat for reference |
| Last Updated | Date | When this record was last updated from Street Manager |
| Source Event | Rich text | Last event_type that triggered an update |

**Note:** "Actual End" from the original spec is not currently populated — Street Manager `WORK_STOP` events may not include this field in the SNS notification payload. Will be added once we can verify the actual data format from live notifications.

**Notion views to create manually:**

- **All Active** — filter: Work Status is not "Completed" and not "Cancelled", sort by Proposed Start descending
- **High Impact** — filter: Cycling Impact is "High", Work Status is not "Completed"
- **By Borough** — grouped by Borough, filtered to active works
- **Lambeth Only** — filter: Borough is "Lambeth"
- **Southwark Only** — filter: Borough is "Southwark"
- (etc. for each borough)
- **Road Closures** — filter: Traffic Management is "Road closure", Work Status is not "Completed"
- **This Week** — filter: Proposed Start is within this week

### 6.2 Traffic Orders Database (Phase 4 — D-TRO) — IN PROGRESS

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | TRO name from D-TRO data (e.g. "License (Other) on Landor Road") |
| D-TRO ID | Rich text | D-TRO UUID — primary key for dedup (e.g. `d268d055-66c1-40cd-ab07-31237c6974d1`) |
| D-TRO Reference | Rich text | Publisher's reference number (e.g. `145873525`) |
| Borough | Select | Which target borough |
| Regulation Type | Multi-select | Values from D-TRO data: miscRoadClosure / kerbsideNoWaiting / kerbsideParkingPlace / kerbsidePermitParkingPlace / kerbsideDisabledBadgeHoldersOnly / kerbsideLoadingPlace / kerbsideTaxiRank / speedLimit / oneWay / weightLimit / cycleLane / busLane / other |
| Location Description | Rich text | Human-readable location (from troName or provision geometry) |
| Street Name | Rich text | If available from provision data |
| Made Date | Date | When the order was made/signed |
| Effective Date | Date | When the order comes into force (`comingIntoForceDate`) |
| End Date | Date | If temporary |
| Authority | Rich text | Traffic regulation authority name (`traName`, e.g. "LONDON BOROUGH OF LAMBETH") |
| Action Type | Select | new / amendment / revocation |
| Cycling Impact | Select | Positive / Negative / Neutral / Needs Review |
| Cycling Summary | Rich text | Claude-generated assessment |
| Coordinates | Rich text | WGS84 lon,lat (from provision geometry, if available) |
| Schema Version | Rich text | D-TRO schema version (e.g. "3.4.0") |
| Last Updated | Date | When this record was last updated |

**Notion views for Traffic Orders:**

- **All Orders** — sort by Effective Date descending
- **Road Closures** — filter: Regulation Type contains "miscRoadClosure"
- **By Borough** — grouped by Borough
- **Cycling Relevant** — filter: Cycling Impact is "Positive" or "Negative"
- **Recent** — filter: Effective Date is within last 30 days

### 6.3 TfL Disruptions Database (Phase 2) — DONE

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Location + category (auto-generated) |
| TfL Disruption ID | Rich text | Unique ID from TfL API |
| Borough | Select | Which target borough |
| Category | Select | Works / Collisions / Hazards / Network delays / Asset issues / Breakdowns / Planned events |
| Sub-Category | Rich text | More specific cause description |
| Status | Select | Active / Scheduled / Resolved |
| Severity | Rich text | TfL severity level |
| Location | Rich text | TfL text description |
| Corridors | Rich text | Affected road corridors |
| Start Time | Date | When the disruption starts/started |
| End Time | Date | When the disruption is expected to end |
| Description | Rich text | TfL comments/description (truncated if long) |
| Cycling Impact | Select | High / Medium / Low / Minimal |
| Cycling Summary | Rich text | Claude-generated summary (if applicable) |
| Coordinates | Rich text | WGS84 lon,lat |
| Last Updated | Date | When this record was last updated |

### 6.4 Cycling Collisions Database (Phase 3) — DONE

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Location + date (auto-generated, e.g. "Brixton Road / Stockwell Rd — 14 Mar 2024") |
| Collision Reference | Rich text | STATS19 accident_index |
| Borough | Select | Which target borough |
| Date | Date | Date of collision |
| Time | Rich text | Time of collision (HH:MM) |
| Severity | Select | Fatal / Serious / Slight |
| Number of Cyclists Hurt | Number | Count of pedal cycle casualties in this collision |
| Worst Cyclist Severity | Select | Fatal / Serious / Slight |
| Other Vehicles | Rich text | Types of other vehicles involved (e.g. "Car", "HGV", "Bus") |
| Road Name | Rich text | First road / location description |
| Speed Limit | Number | Speed limit at collision location (mph) |
| Junction Detail | Rich text | Junction type if applicable |
| Light Conditions | Select | Daylight / Darkness - lights lit / Darkness - no lights / Other |
| Weather | Select | Fine / Rain / Snow / Fog / Other |
| Road Surface | Select | Dry / Wet / Frost / Snow / Flood |
| Coordinates | Rich text | WGS84 lon,lat |
| Data Year | Rich text | Which STATS19 data release this came from |

**Notion views for Collisions:**

- **All Cyclist Collisions** — sort by Date descending
- **Fatal & Serious Only** — filter: Severity is "Fatal" or "Serious"
- **By Borough** — grouped by Borough
- **By Road** — grouped/sorted by Road Name to identify dangerous roads
- **Involving HGVs** — filter: Other Vehicles contains "HGV" or "Goods Vehicle"
- **Heatmap export** — all collisions with coordinates, for export to mapping tools

### 6.5 Development Activity Database (Phase 6) — NOT STARTED

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Site address + application type (auto-generated) |
| Application Reference | Rich text | Planning application reference |
| Borough | Select | Which target borough |
| Site Address | Rich text | Full site address |
| Application Type | Rich text | e.g. "Full Planning Application", "Reserved Matters" |
| Development Type | Rich text | e.g. "Major Residential", "Commercial", "Mixed Use" |
| Description | Rich text | Proposal description (truncated) |
| Status | Select | Submitted / Under Consideration / Approved / Refused / Withdrawn |
| Decision Date | Date | If decided |
| Cycling Impact | Select | Positive / Negative / Neutral / Needs Review |
| Cycling Summary | Rich text | Claude-generated assessment of transport/cycling implications |
| Coordinates | Rich text | WGS84 lon,lat |
| PLD Link | URL | Link to the application in the Planning London Datahub |
| Last Updated | Date | When this record was last updated |

---

## 7. Implementation Plan

### Phase 1: Street Manager Integration (MVP) — DONE

All items complete. Activity and Section 58 subscriptions confirmed. 

1. **Project setup** — DONE
   - Python project with `pyproject.toml` and Dockerfile
   - Dependencies: `fastapi`, `uvicorn`, `httpx`, `shapely`, `pyproj`, `notion-client==2.2.1`, `anthropic`, `pydantic-settings`, `cryptography`
   - Environment variable configuration via `pydantic-settings`

2. **Borough boundary loader** — DONE
   - Downloaded from ONS Open Geography Portal (ArcGIS API, GeoJSON format)
   - 8 boroughs loaded and verified with real coordinate tests

3. **SNS webhook receiver** — DONE
   - FastAPI app with POST endpoint at `/webhook/street-manager`
   - SNS subscription confirmation (auto-fetches SubscribeURL)
   - SNS message signature verification (cryptographic, using AWS signing certificates)
   - Filters to relevant event types only

4. **Geo-filter pipeline** — DONE
   - Two-tier filter: SWA code fast path + BNG→WGS84 point-in-polygon
   - Tested with real borough boundaries (Brixton Road→Lambeth, Borough High Street→Southwark, Canary Wharf→rejected)

5. **Deduplication** — DONE
   - In-memory cache of `permit_reference → Notion page_id`, warmed from Notion at startup
   - Falls back to Notion query on cache miss
   - Creates new pages or updates existing ones based on permit reference

6. **Notion writer** — DONE
   - Upsert with dedup query
   - Property mapping for all schema fields

7. **Cycling impact classifier** — DONE
   - Rule-based quick classification (all works)
   - Optional Claude Haiku enrichment (high/medium impact only)

8. **Deployment to Railway** — DONE
   - Dockerfile with dynamic `$PORT` binding
   - Health check endpoint at `/health`
   - `railway.json` for healthcheck config

### Phase 2: TfL Live Disruptions — DONE

All items complete. Polling live, writing to Notion.

1. **TfL API access** — DONE. Works without API key at lower rate limits. Optional `TFL_API_KEY` env var supported.
2. **TfL disruptions client** (`src/tfl/disruptions.py`) — DONE
   - Fetches from `GET https://api.tfl.gov.uk/Road/all/Disruption`
   - Extracts WGS84 coordinates from GeoJSON `geography` field (Point or LineString centroid)
   - Classifies cycling impact based on real TfL categories: Collisions/Hazards→high, Moderate severity→medium, Minimal Works→low
3. **Disruptions pipeline** (`src/tfl/pipeline.py`) — DONE
   - Polls daily at 09:00 UK time (+ initial poll on startup)
   - Geo-filters against borough polygons (reuses `GeoFilter.check_wgs84_point()`)
   - Optional Claude Haiku summary for high/medium impact
   - Upserts to Notion, marks disappeared disruptions as Resolved
4. **Notion Disruptions database** — DONE. Schema from Section 6.3.
5. **Notion writer extension** — DONE. Dedup on `TfL Disruption ID`, separate cache.
6. **Env vars added:** `TFL_API_KEY` (optional), `NOTION_DISRUPTIONS_DB_ID`
7. **Tests:** 17 new tests (classification, geo extraction, Notion property mapping)

**New files:** `src/tfl/__init__.py`, `src/tfl/disruptions.py`, `src/tfl/pipeline.py`, `tests/test_tfl_disruptions.py`
**Modified files:** `src/main.py` (asyncio poller task), `src/config.py` (new env vars), `src/geo/filter.py` (`check_wgs84_point()`), `src/notion/writer.py` (disruptions cache + upsert), `src/notion/schemas.py` (`disruption_to_notion_properties()`), `src/classifier/claude.py` (`get_disruption_cycling_summary()`)

### Phase 3: STATS19 Cycling Collision Data — DONE

**Priority: HIGH.** The most powerful dataset for cycling advocacy. Implementation is straightforward (CSV download + filter + Notion write), but it's a batch job rather than real-time.

1. **Collision data importer** (`src/stats19/importer.py`)
   - Downloads collision, casualty, and vehicle CSVs from DfT road safety open data
   - Uses stdlib `csv` module (no pandas dependency needed)
   - Filters collisions to those within target borough polygons (coordinates are WGS84, same geo-filter reused)
   - Joins to casualties table, filters to rows where `casualty_type == 1` (pedal cyclist)
   - Joins to vehicles table to identify other vehicle types involved (deduped)
   - Maps all coded integer values to human-readable labels (severity, vehicle type, light conditions, weather, road surface, junction detail)
   - Supports single-year download or last-5-years combined file
2. **Notion Cycling Collisions database** created with schema from Section 6.4
3. **Notion writer extension** — collision cache, warm, find, upsert methods (dedup on `collision_index`)
4. **Backfill script** (`scripts/backfill_collisions.py`) — `python -m scripts.backfill_collisions [--year 2024]` or omit `--year` to default to last 5 years
5. **Scheduled updates** — run manually when new STATS19 data drops. 2025 final data is scheduled for September 2026. Initial backfill of 2020–2024 completed 12 March 2026
6. **Env var:** `NOTION_COLLISIONS_DB_ID` configured in Railway

**Files:** `src/stats19/__init__.py`, `src/stats19/importer.py`, `scripts/backfill_collisions.py`
**Tests:** 14 tests in `tests/test_stats19.py` (filtering, severity mapping, vehicle dedup, road name building, Notion property mapping, lookup tables)

### Phase 4: D-TRO Integration — DONE

All items complete. 116 D-TROs backfilled (112 Lambeth, 1 Lewisham, 3 Croydon). Other target boroughs not yet publishing.

1. **Explore the D-TRO API** — DONE. Auth: OAuth2 client credentials (API Key + API Secret → bearer token, 30 min TTL). Production base: `https://dtro.dft.gov.uk/v1`. Endpoints: `POST /search` (filter by `traCreator` SWA code, max page size 50), `GET /dtros/<id>`, `POST /events` (changes since timestamp). Schema v3.4.0.
2. **Verify Lambeth is publishing** — DONE. Lambeth has 112 D-TROs (road closures, parking suspensions, cycle lane closures via AppyWay). Lewisham has 1 (parking consolidation), Croydon has 3 (road closures).
3. **D-TRO client** (`src/dtro/client.py`) — DONE. OAuth2 token management with auto-refresh, search by TRA code, fetch by ID, events endpoint.
4. **D-TRO pipeline** (`src/dtro/pipeline.py`) — DONE. Extracts details from full D-TRO records (regulation types, street names from regulationLocation places, BNG→WGS84 coordinates, time validity). Rule-based cycling impact classifier: road/cycle lane closures = Negative, new cycle lanes = Positive, parking-only = Neutral, others = Needs Review. Optional Claude Haiku summary for Negative/Needs Review.
5. **Notion Traffic Orders database** — DONE. Schema from Section 6.2 (updated with D-TRO ID, multi-select regulation types, action type, schema version). Backfill of 116 D-TROs completed 12 March 2026.
6. **Backfill script** (`scripts/backfill_traffic_orders.py`) — `python -m scripts.backfill_traffic_orders`
7. **Env vars:** `DTRO_APP_ID`, `DTRO_API_KEY`, `DTRO_API_SECRET`, `NOTION_TRAFFIC_ORDERS_DB_ID` — configured in Railway and `.env`
8. **Tests:** 25 tests (classifier for all regulation types, detail extraction, street name cleaning, coordinate conversion, Notion property mapping)

**New files:** `src/dtro/__init__.py`, `src/dtro/client.py`, `src/dtro/pipeline.py`, `scripts/backfill_traffic_orders.py`, `scripts/explore_dtro.py`, `tests/test_dtro.py`
**Modified files:** `src/config.py` (new env vars), `src/notion/writer.py` (traffic orders cache + upsert), `src/notion/schemas.py` (`traffic_order_to_notion_properties()`, `_multi_select()`), `src/classifier/claude.py` (`get_traffic_order_cycling_summary()`)

### Phase 5: TfL Cycling Infrastructure Database (CID) — DONE

**Completed 14 March 2026.** Loads cycling infrastructure as a static spatial reference layer at startup. Roadworks, disruptions, and traffic orders near cycling infrastructure get their impact rating automatically upgraded (never downgraded). Named Cycleway routes (Cycleway 5, 7, etc.) are also loaded from TfL's ArcGIS FeatureServer.

**Data sources:**
- CID cycle lanes/tracks: `https://cycling.data.tfl.gov.uk/CyclingInfrastructure/data/lines/cycle_lane_track.json` (~29MB, ~25k features all-London, pre-filtered to target boroughs)
- CID restricted routes (modal filters): `https://cycling.data.tfl.gov.uk/CyclingInfrastructure/data/lines/restricted_route.json` (~1.6MB, ~1.4k features)
- TfL Cycleway routes: ArcGIS FeatureServer at `services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Cycle_Routes/FeatureServer/11` (146 features, all open routes)

**Implementation:**
1. `scripts/download_cid.py` — downloads and pre-filters CID data to target boroughs, saves to `data/`. Run at Docker build time.
2. `src/geo/cycling_infrastructure.py` — `CyclingInfrastructureIndex` class using Shapely STRtree (no extra dependency). Loads from pre-filtered JSON files, builds spatial index for 50m proximity queries. Returns `CIDResult` with asset type, description, distance, and route name.
3. `src/classifier/rules.py` — `upgrade_impact_with_cid()`: upgrade-only logic. Near segregated/stepped/partially-segregated cycleway or named Cycleway route → upgrade to "high". Near modal filter, mandatory/advisory/contraflow lane → upgrade to at least "medium". Shared use paths → no upgrade.
4. All three pipelines (Street Manager, TfL Disruptions, D-TRO) check CID proximity after rule-based classification. For D-TRO, Neutral → Needs Review if near cycling infra.
5. New Notion field "Nearby Cycling Infrastructure" on all three databases, e.g. "Cycleway 7 — Segregated cycle track (12m)". Auto-created at startup via `ensure_cid_property()` in NotionWriter if the property doesn't already exist.

**Priority order** when multiple matches: named Cycleway route > segregated > stepped > partially segregated > mandatory > modal filter > contraflow > advisory > shared use

**New files:** `src/geo/cycling_infrastructure.py`, `scripts/download_cid.py`, `tests/test_cycling_infrastructure.py` (34 tests)
**Modified files:** `src/classifier/rules.py`, `src/pipeline.py`, `src/tfl/pipeline.py`, `src/dtro/pipeline.py`, `src/main.py`, `src/notion/schemas.py`, `src/notion/writer.py`, `Dockerfile`, `.gitignore`
**No new dependencies** — STRtree is built into Shapely (already installed)
**Data files (gitignored, downloaded at build):** `data/cid_cycle_lanes.json`, `data/cid_restricted_routes.json`, `data/cycle_routes.json`

### Phase 6: Planning London Datahub — NOT STARTED

**Priority: LOWER.** Strategic intelligence rather than immediate operational awareness. Useful for identifying developments that will generate construction traffic or trigger highway changes, but less directly actionable than the other data sources.

1. **Explore the PLD API** — review technical documentation at https://www.london.gov.uk/programmes-strategies/planning/digital-planning/planning-london-datahub
2. **PLD client** (`src/planning/client.py`) — daily poll for new/updated applications in target boroughs
3. **Filter to major applications** — those likely to have transport implications (major residential, commercial, infrastructure)
4. **Claude classification** — assess cycling relevance from application description (construction traffic impact, S278 highway works, cycle parking provision, new connections)
5. **Create Notion Development Activity database** with schema from Section 6.5
6. **Add env vars:** `NOTION_DEVELOPMENT_DB_ID`

**New files:** `src/planning/__init__.py`, `src/planning/client.py`

### Phase 7: Enhancements — NOT STARTED

- **USRN enrichment:** Build a lookup of key cycling routes by USRN, flag works on these routes as automatically high-priority
- **Historical analysis:** Aggregate data over time to identify most-disrupted roads per borough (à la Chris Carlon's analysis)
- **Notification emails:** Send weekly digest or instant alerts for high-impact works to borough group mailing lists
- **Web dashboard:** Simple public page showing active high-impact works on a map (could be a static site on Vercel)
- **Agenda integration:** The lambeth-cyclists-claude email bot (separate project at `C:\Users\charl\ClaudeProjects\lambeth-cyclists-claude`) could pull from this Notion database when generating meeting agendas

---

## 8. Key Technical Decisions

### Why SNS push rather than polling?

Street Manager's open data service uses AWS SNS for near-real-time notifications. **This is the only open data access method** — the REST API (`GET /works/updates`) requires an authenticated organizational account (highway authority/utility company role), which is not available to open data consumers. Railway provides the public HTTPS endpoint for SNS delivery; no AWS account is needed.

### Why not use OS Data Hub?

The OS Data Hub would add a runtime API dependency, rate limits, and an API key to manage. Since we only need borough boundary polygons (which are static data), downloading them once from the ONS Open Geography Portal is simpler and more reliable.

### Why Notion rather than a database?

Notion is already the Lambeth Cyclists workspace. The whole point is to put this data where the group already works. Notion's filtering and view capabilities are good enough for the use case, and non-technical group members can use it without any training. If performance becomes an issue (unlikely at borough-level volumes), we could add a PostgreSQL layer later.

### Why Claude for classification?

A simple rule-based classifier handles most cases, but some works benefit from contextual understanding — e.g. knowing that a "minor" work with "some carriageway restriction" on a narrow one-lane street is actually high impact for cycling, or that a road closure on a quiet residential street matters less than one on a main cycling corridor. Claude can provide this nuance. But it's optional and only used for high/medium impact works to control costs.

### Why notion-client v2.2.1?

The `notion-client` Python package removed `databases.query()` in versions after 2.2.x. This method is essential for querying the Notion database by permit reference (for deduplication). Pinned to v2.2.1 to match the version used by the lambeth-cyclists-claude project.

### Coordinate system handling

Street Manager uses British National Grid (EPSG:27700) throughout. Borough boundaries from ONS are in WGS84 (EPSG:4326). Incoming coordinates are converted to WGS84 using pyproj at processing time, and stored in WGS84 format in Notion.

---

## 9. Registration Steps

| Step | Status | Notes |
|------|--------|-------|
| Street Manager Open Data | SUBMITTED 8 Mar 2026 | Awaiting subscription confirmation POST from DfT. Endpoint: `https://lambeth-cyclists-street-manager-production.up.railway.app/webhook/street-manager`. Initial confirmation POST returned 502 due to port misconfiguration (now fixed). DfT helpdesk: https://streetmanager.atlassian.net/servicedesk/customer/portals |
| Notion Integration | DONE | Integration created, Roadworks database shared with it |
| Notion Roadworks Database | DONE | Created with schema from Section 6.1 |
| Anthropic API Key | DONE | Configured in Railway env vars |
| TfL API Key registration | DONE (not needed) | Works without key at lower rate limits. Optional `TFL_API_KEY` env var supported |
| Notion Disruptions Database | DONE | Created with schema from Section 6.3. DB ID configured in Railway env vars |
| STATS19 data download | DONE | Phase 3 — downloads from https://data.dft.gov.uk/road-accidents-safety-data/. Individual years 2020–2024 available, plus last-5-years combined file. 2025 final data due Sep 2026 |
| Notion Cycling Collisions Database | DONE | Phase 3 — created, DB ID configured in Railway env vars. Backfill of 2020–2024 completed 12 Mar 2026 |
| D-TRO Service registration | DONE | Phase 4 — registered at https://dltro-ui.gov.uk, app credentials obtained 12 Mar 2026. Env vars: `DTRO_APP_ID`, `DTRO_API_KEY`, `DTRO_API_SECRET` |
| Notion Traffic Orders Database | DONE | Phase 4 — created, DB ID configured in Railway env vars. Backfill of 116 D-TROs completed 12 Mar 2026 |
| TfL CID data download | DONE | Phase 5 — downloaded at Docker build time via `scripts/download_cid.py`. Pre-filtered to target boroughs. Includes cycle lanes/tracks, restricted routes, and Cycleway routes from ArcGIS. Note: TfL CDN blocks Python's default User-Agent; script sends a custom header. |
| Notion "Nearby Cycling Infrastructure" property | DONE | Phase 5 — auto-created at startup via `ensure_cid_property()` on all 3 databases (roadworks, disruptions, traffic orders). No manual Notion setup needed. |
| Planning London Datahub exploration | NOT STARTED | Phase 6 |
| Notion Development Activity Database | NOT STARTED | Phase 6 |

---

## 10. SWA Code Reference

Borough SWA codes for fast-path filtering. Verified against the official GeoPlace SWA_ORG_ACTIVE registry (March 2026):

| Borough | SWA Code |
|---------|----------|
| Lambeth | 5660 |
| Southwark | 5840 |
| Wandsworth | 5960 |
| Lewisham | 5690 |
| Merton | 5720 |
| Croydon | 5240 |
| City of London | 5030 |
| Westminster | 5990 |
| Transport for London | 20 |

These are hardcoded in `src/config.py`. Source: https://www.geoplace.co.uk/local-authority-resources/street-works-managers/view-swa-codes

**Note:** The original codes (from the spec's Section 10) were incorrect — they mapped to the wrong boroughs (e.g. 5210 was Camden, not Croydon; 5540 was Hounslow, not Lambeth). Corrected in March 2026 after verifying against GeoPlace registry. The TfL code in GeoPlace is listed as numeric 20; Street Manager may format this as "20" or "0020" — needs verification from live permit notifications.

---

## 11. Error Handling & Resilience

- **SNS delivery failures:** AWS SNS retries up to 20 times over approximately one hour. The app is designed to always return 200 for valid (signed) messages, even if downstream processing fails, to prevent SNS from retrying already-processed messages.
- **SNS signature verification:** All incoming messages are cryptographically verified against AWS signing certificates. Unsigned or spoofed requests are rejected with 403. Exception: `SubscriptionConfirmation` messages are processed even if signature verification fails, since the `SubscribeURL` is a one-time self-validating token.
- **Request logging:** Incoming notifications are logged at INFO level with event type and object reference. Full headers/body logging was used during initial setup and removed once the subscription was confirmed.
- **Notion API rate limits:** The Notion API has rate limits (currently 3 requests/second). Basic backoff implemented on failure.
- **Malformed notifications:** Logged and skipped. The process never crashes on bad input.
- **Startup resilience:** If Notion cache warming or borough boundary loading fails, the app still starts in "degraded" mode — the health endpoint responds, but notifications won't be processed. This prevents Railway from entering a restart loop.
- **Health check:** `GET /health` returns status (`ok`, `starting`, or `degraded`), uptime, last notification timestamp, and notification count.

---

## 12. Project Structure (Actual)

```
lambeth-cyclists-street-manager/
├── south-london-street-works-monitor.md   # This document
├── pyproject.toml
├── Dockerfile
├── railway.json
├── .env.example
├── .gitignore
├── data/
│   └── london_boroughs.geojson            # 8 borough boundaries from ONS (static)
├── src/
│   ├── __init__.py
│   ├── main.py                            # FastAPI app, lifespan, /health endpoint
│   ├── config.py                          # Pydantic settings, SWA code mapping
│   ├── pipeline.py                        # Notification processing pipeline
│   ├── geo/
│   │   ├── __init__.py
│   │   ├── boundaries.py                  # Borough polygon loading from GeoJSON
│   │   └── filter.py                      # Two-tier geo-filter + BNG→WGS84
│   ├── street_manager/
│   │   ├── __init__.py
│   │   ├── webhook.py                     # SNS webhook handler
│   │   └── sns_verify.py                  # SNS message signature verification
│   ├── tfl/
│   │   ├── __init__.py
│   │   ├── disruptions.py                 # TfL API client, geo extraction, classifier
│   │   └── pipeline.py                    # Fetch → filter → classify → Notion
│   ├── dtro/
│   │   ├── __init__.py
│   │   ├── client.py                      # D-TRO API OAuth2 + search/fetch
│   │   └── pipeline.py                    # D-TRO → classify → Notion
│   ├── stats19/
│   │   ├── __init__.py
│   │   └── importer.py                    # STATS19 CSV download, filter, Notion mapping
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── rules.py                       # Rule-based cycling impact classification
│   │   └── claude.py                      # Claude Haiku enrichment (optional)
│   └── notion/
│       ├── __init__.py
│       ├── writer.py                      # Notion upsert with dedup
│       └── schemas.py                     # Work data → Notion property mapping
├── tests/
│   ├── __init__.py
│   ├── test_geo_filter.py                 # BNG conversion + filter tests
│   ├── test_classifier.py                 # Rule-based classifier tests
│   ├── test_webhook.py                    # SNS webhook + signature tests
│   ├── test_notion_schemas.py             # Property mapping tests
│   ├── test_integration.py                # Real boundary data tests
│   ├── test_tfl_disruptions.py            # TfL classifier, geo, schema tests
│   ├── test_stats19.py                    # STATS19 filtering, mapping, lookup tests
│   ├── test_dtro.py                       # D-TRO classifier, extraction, schema tests
│   └── fixtures/
│       ├── sample_permit_notification.json
│       └── sample_tfl_notification.json
└── scripts/
    ├── backfill_collisions.py             # STATS19 backfill: python -m scripts.backfill_collisions
    ├── backfill_traffic_orders.py         # D-TRO backfill: python -m scripts.backfill_traffic_orders
    ├── download_cid.py                    # CID data download: python -m scripts.download_cid (run at Docker build)
    └── explore_dtro.py                    # D-TRO API explorer: python -m scripts.explore_dtro
```

---

## 13. Testing Strategy

128 tests passing. Coverage:

- **Geo-filtering (11 tests):** BNG→WGS84 conversion with known coordinates, SWA code fast path, point-in-polygon with real borough boundaries (Brixton Road→Lambeth, Borough High Street→Southwark, Streatham→Lambeth, Croydon town centre→Croydon), rejection of coordinates outside target area (Canary Wharf, Islington).
- **Classification (8 tests):** All traffic management types, emergency works, footway vs carriageway, unknown types.
- **Webhook (7 tests):** Health endpoint, valid notifications, irrelevant events, malformed body, unsigned message rejection, unknown SNS types, subscription confirmation signature bypass.
- **Notion schemas (3 tests):** Basic property mapping, missing fields, optional fields omitted.
- **Integration (4 tests):** Real boundary data loading, real coordinate matching.
- **TfL disruptions (17 tests):** Impact classification for all real TfL categories (Collisions, Hazards, Works, Breakdowns, Planned events, Network delays), severity handling, GeoJSON point/linestring extraction, null geography handling, Notion property mapping with full/missing/summary fields.
- **STATS19 collisions (14 tests):** Filtering by casualty type, severity mapping, vehicle type dedup, road name building, Notion property mapping, lookup table coverage.
- **D-TRO traffic orders (25 tests):** Cycling impact classification for all regulation types (road closure, cycle lane closure, one-way, cycle lane, parking, loading, speed limit, mixed), detail extraction from full D-TRO records (regulation types, street names, coordinate conversion, time validity, provision description), Notion property mapping (multi-select, dates, coordinates, optional summary).
- **Cycling infrastructure / CID (34 tests):** CIDResult formatting (with/without route name, zero distance), cycle lane classification (all 7 lane types, unknown defaults, priority ordering), spatial index (empty index, nearby feature detection, far feature rejection, priority ordering of cycleway route over advisory and segregated over modal filter, feature count), file loading (from GeoJSON files, empty directory, filtering non-open routes), impact upgrade logic (13 tests covering all upgrade/no-downgrade scenarios for every asset type).

---

## 14. Related Projects

- **lambeth-cyclists-claude** (`C:\Users\charl\ClaudeProjects\lambeth-cyclists-claude`): Email bot that monitors Gmail and writes to Notion. Uses the same stack (Python, notion-client, anthropic, Railway). Future enhancement: its agenda generation module could query the Roadworks Notion database from this project to include upcoming roadworks in meeting agendas.

---

## Appendix A: Useful Links

**Street Manager (Phase 1 — DONE):**
- Street Manager docs: https://department-for-transport-streetmanager.github.io/street-manager-docs/
- Street Manager open data: https://department-for-transport-streetmanager.github.io/street-manager-docs/open-data/
- Street Manager API notifications: https://department-for-transport-streetmanager.github.io/street-manager-docs/api-notifications/
- Street Manager helpdesk: https://streetmanager.atlassian.net/servicedesk/customer/portals
- Street Manager Python client: https://github.com/cogna-public/streetmanager

**TfL Live Disruptions (Phase 2):**
- TfL Unified API Swagger: https://api.tfl.gov.uk/swagger/ui/index.html
- TfL API portal (registration): https://api-portal.tfl.gov.uk/
- TfL open data overview: https://tfl.gov.uk/info-for/open-data-users/our-open-data
- TfL Live Traffic Disruptions (London Datastore): https://data.london.gov.uk/dataset/tfl-live-traffic-disruptions-248xn/

**STATS19 Road Collision Data (Phase 3):**
- STATS19 open data downloads: https://www.gov.uk/government/statistical-data-sets/road-safety-open-data
- STATS19 data guide (Excel, decode values): available at the link above
- DfT pedal cycle factsheet 2024: https://www.gov.uk/government/statistics/reported-road-casualties-great-britain-pedal-cyclist-factsheet-2024
- TfL road safety data page: https://tfl.gov.uk/corporate/publications-and-reports/road-safety
- `stats19` R package (reference for data structure): https://itsleeds.github.io/stats19/

**D-TRO (Phase 4):**
- D-TRO GitHub: https://github.com/department-for-transport-public/D-TRO
- D-TRO service: https://dltro-ui.gov.uk
- Lambeth digital traffic orders (AppyWay case study): https://appyway.com/portfolio/unlocking-sustainability-lambeth-council-implements-d-tros-and-uses-traffic-suite-to-manage-and-monitor-their-sustainable-kerbside-vision/

**TfL Cycling Infrastructure Database (Phase 5):**
- CID data downloads: https://cycling.data.tfl.gov.uk/ (under CycleInfrastructure/)
- CID on London Datastore: https://data.london.gov.uk/dataset/cycling-infrastructure-database-23n1k/
- CID OSM wiki: https://wiki.openstreetmap.org/wiki/TfL_Cycling_Infrastructure_Database

**Planning London Datahub (Phase 6):**
- PLD main page: https://www.london.gov.uk/programmes-strategies/planning/digital-planning/planning-london-datahub
- PLD API technical docs: https://www.london.gov.uk/sites/default/files/planninglondondatahub_api_connection_technical_documentation_v1.pdf
- Lambeth Open Digital Planning: https://www.lambeth.gov.uk/better-fairer-lambeth/projects/open-digital-planning

**General / Inspiration:**
- ONS Open Geography Portal: https://geoportal.statistics.gov.uk/
- London Datastore boundaries: https://data.london.gov.uk/dataset/statistical-gis-boundary-files-london
- Chris Carlon's Street Works analysis (inspiration): https://www.ccarlon.dev/blog/street_works/
- Transport select committee report on street works: https://publications.parliament.uk/pa/cm5901/cmselect/cmtrans/522/report.html
- Lambeth statutory consultations: https://www.lambeth.gov.uk/streets-roads-and-transport/traffic-and-road-closures/road-humps-stopping-orders-and/statutory-consultations
- Southwark Cyclists consultations page: https://southwarkcyclists.org.uk/current-consultations/
