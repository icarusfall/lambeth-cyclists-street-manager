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
| 1 | Deduplication (via Notion queries + in-memory cache) | DONE |
| 1 | Notion writer | DONE |
| 1 | Cycling impact classifier (rule-based) | DONE |
| 1 | Claude API enrichment (optional, for high/medium) | DONE |
| 1 | Deployment to Railway | DONE |
| 1 | Street Manager open data registration | SUBMITTED — awaiting confirmation (up to 1 working day) |
| 1 | Notion Roadworks database created & connected | DONE |
| 1 | Tests (32 passing) | DONE |
| 2 | D-TRO integration | NOT STARTED |
| 2 | Traffic Orders Notion database | NOT STARTED |
| 3 | USRN enrichment, historical analysis, alerts, dashboard | NOT STARTED |

### Changes from Original Spec

1. **SNS-only architecture (not polling).** The Street Manager open data feed is SNS-only — there is no public REST API or CSV export for open data consumers. The REST API (`GET /works/updates`) requires an authenticated organizational account (highway authority/utility company). Railway provides the HTTPS endpoint for SNS; no AWS account is needed.

2. **No `schedule`/`apscheduler` needed.** Since we're using SNS push (not polling), there are no scheduled jobs in Phase 1. The app is purely event-driven. Scheduled jobs will be added in Phase 2 for D-TRO polling.

3. **Deduplication via Notion, not local JSON file.** Railway containers can restart and lose local state. Instead, the app queries Notion by `permit_reference_number` to check for existing records before creating new ones. An in-memory cache (warmed at startup from Notion) avoids per-item Notion queries during normal operation.

4. **`notion-client` pinned to v2.2.1.** Version 2.3+ removed `databases.query()`. Pinned to match the version used by the lambeth-cyclists-claude project.

5. **`pydantic-settings` target_boroughs is a string, not a list.** Pydantic-settings v2 tries to JSON-parse `list[str]` fields from env vars, which fails for comma-separated strings. Changed to a `str` field with a `get_target_boroughs()` method that splits on commas.

6. **SNS signature verification added.** The original spec noted this was missing. Now implemented using the `cryptography` package to validate SNS message signatures against AWS signing certificates.

7. **SWA codes corrected.** The env var example in the original spec (`5660,5630,...`) didn't match the table in Section 10. The implemented codes match the Section 10 table. These still need verification against the live Street Manager API once notifications start flowing.

8. **Borough boundaries sourced from ONS, not London Datastore.** The London Datastore provides shapefiles, not GeoJSON. Used the ONS Open Geography Portal ArcGIS API instead (`Local_Authority_Districts_December_2024_Boundaries_UK_BFE`), which provides GeoJSON directly. Property key for borough names is `LAD24NM`.

9. **Removed planned files that weren't needed.** `parser.py`, `poller.py`, `state/dedup.py`, `dtro/client.py`, and `scripts/backfill.py` from the original structure were not created — the SNS architecture is simpler and doesn't need them. Added `pipeline.py` and `sns_verify.py` instead.

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

**Status:** Registration submitted 8 March 2026. Awaiting confirmation (up to 1 working day). The endpoint registered is `https://lambeth-cyclists-street-manager-production.up.railway.app/webhook/street-manager`.

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

**API type:** REST API at https://d-tro.dft.gov.uk

**Registration:** Free at the URL above.

**Status:** Beta — coverage for London boroughs likely still patchy. Deferred to Phase 2 — verify data availability before building.

**GitHub:** https://github.com/department-for-transport-public/D-TRO — contains data model docs, schema files, and example data for the current spec version (3.5.0).

### 2.3 Borough Boundary Data — Geographic Filtering

**What:** GeoJSON polygon boundaries for London boroughs, used to determine whether a roadwork/order falls within our target area.

**Source used:** ONS Open Geography Portal ArcGIS REST API — `Local_Authority_Districts_December_2024_Boundaries_UK_BFE` dataset. Downloaded as GeoJSON directly via API query, stored in repo as `data/london_boroughs.geojson`. Property key for borough names: `LAD24NM`.

**Why ONS and not London Datastore:** The London Datastore provides shapefiles (requiring conversion), while the ONS portal serves GeoJSON directly via its ArcGIS API.

**Coordinate systems:** Street Manager uses British National Grid (EPSG:27700). Borough boundaries are in WGS84 (EPSG:4326). Incoming BNG coordinates are converted to WGS84 using `pyproj` at processing time.

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
┌──────────────────────────────────────────────┐
│          Python Daemon (Railway)              │
│  lambeth-cyclists-street-manager-production   │
│  .up.railway.app                             │
│                                              │
│  ┌─────────────┐                             │
│  │ FastAPI      │                             │
│  │ webhook      │                             │
│  │ receiver     │                             │
│  │ + SNS sig    │                             │
│  │   verify     │                             │
│  └──────┬───────┘                             │
│         │                                    │
│         ▼                                    │
│  ┌──────────────────────────────────────┐     │
│  │        Geo-Filter Engine             │     │
│  │  1. SWA code check (fast path)       │     │
│  │  2. BNG→WGS84 + point-in-polygon    │     │
│  │  Borough boundaries loaded at start  │     │
│  └──────────────┬───────────────────────┘     │
│                 │                              │
│                 ▼                              │
│  ┌──────────────────────────────────────┐     │
│  │     Cycling Impact Classifier        │     │
│  │  - Rule-based (all works)            │     │
│  │  - Claude Haiku summary (high/med)   │     │
│  └──────────────┬───────────────────────┘     │
│                 │                              │
│                 ▼                              │
│  ┌──────────────────────────────────────┐     │
│  │     Notion Writer                    │     │
│  │  - Upsert to Roadworks DB            │     │
│  │  - Dedup via permit_ref query        │     │
│  │  - In-memory cache warmed at start   │     │
│  └──────────────────────────────────────┘     │
│                                              │
└──────────────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────────┐
                    │   Notion Workspace  │
                    │   (Lambeth Cyclists) │
                    │                     │
                    │  ┌───────────────┐  │
                    │  │ Roadworks DB  │  │ ← DONE
                    │  └───────────────┘  │
                    │  ┌───────────────┐  │
                    │  │ Traffic       │  │ ← Phase 2
                    │  │ Orders DB     │  │
                    │  └───────────────┘  │
                    └─────────────────────┘
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

**Removed from original spec:** `BOROUGH_SWA_CODES` (hardcoded in config.py), `STREET_MANAGER_API_EMAIL`/`PASSWORD` (not needed for SNS), `DTRO_API_KEY` (Phase 2), `NOTION_TRAFFIC_ORDERS_DB_ID` (Phase 2).

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
        coords_wkt = object_data.get("works_location_coordinates")
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

Implemented in `src/geo/filter.py`. Tested with real coordinates — Brixton Road correctly resolves to Lambeth, Borough High Street to Southwark, etc.

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

### 6.2 Traffic Orders Database (Phase 2 — D-TRO) — NOT STARTED

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Summary of the order (auto-generated) |
| D-TRO Reference | Rich text | Reference from the D-TRO service |
| Borough | Select | Which target borough |
| Regulation Type | Select | Speed limit / Parking restriction / One-way / Road closure / Weight limit / Cycle lane / Bus lane / Other |
| Location Description | Rich text | Human-readable location |
| Street Name | Rich text | If available |
| Effective Date | Date | When the order takes effect |
| End Date | Date | If temporary |
| Authority | Rich text | Traffic regulation authority |
| Cycling Impact | Select | Positive / Negative / Neutral / Needs Review |
| Cycling Summary | Rich text | Claude-generated assessment |
| Order Status | Select | Proposed / In force / Revoked |
| Coordinates | Rich text | WGS84 lon,lat |
| Last Updated | Date | When this record was last updated |

---

## 7. Implementation Plan

### Phase 1: Street Manager Integration (MVP) — DONE

All items complete. Awaiting Street Manager SNS subscription confirmation only.

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

### Phase 2: D-TRO Integration — NOT STARTED

1. Explore the D-TRO API at https://d-tro.dft.gov.uk
2. Verify data availability for London boroughs before building
3. Implement scheduled polling (daily) — will need `apscheduler` added at this point
4. Geo-filter D-TRO records against borough boundaries
5. Write to Traffic Orders Notion database
6. Add Claude classification for cycling relevance of traffic orders

### Phase 3: Enhancements — NOT STARTED

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
| D-TRO Service registration | NOT STARTED | Phase 2 |
| Notion Traffic Orders Database | NOT STARTED | Phase 2 |

---

## 10. SWA Code Reference

Borough SWA codes for fast-path filtering (**still need verification against live Street Manager data**):

| Borough | SWA Code |
|---------|----------|
| Lambeth | 5540 |
| Southwark | 5630 |
| Wandsworth | 5690 |
| Lewisham | 5420 |
| Merton | 5510 |
| Croydon | 5210 |
| City of London | 5110 |
| Westminster | 5990 |
| Transport for London | 0999 |

These are hardcoded in `src/config.py`. Once live notifications arrive, we can verify them against actual data and update if needed. The geo-filter (point-in-polygon) catches any works that slip through due to incorrect SWA codes, so incorrect codes only affect performance (extra geo-lookups), not correctness.

---

## 11. Error Handling & Resilience

- **SNS delivery failures:** AWS SNS retries up to 20 times over approximately one hour. The app is designed to always return 200 for valid (signed) messages, even if downstream processing fails, to prevent SNS from retrying already-processed messages.
- **SNS signature verification:** All incoming messages are cryptographically verified against AWS signing certificates. Unsigned or spoofed requests are rejected with 403. Exception: `SubscriptionConfirmation` messages are processed even if signature verification fails, since the `SubscribeURL` is a one-time self-validating token.
- **Request logging:** Every incoming POST is logged at INFO level with full headers and body, so requests can be reconstructed from deploy logs even if processing fails.
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
│   └── fixtures/
│       ├── sample_permit_notification.json
│       └── sample_tfl_notification.json
└── scripts/                               # (empty — may be used for backfill later)
```

---

## 13. Testing Strategy

33 tests passing. Coverage:

- **Geo-filtering (11 tests):** BNG→WGS84 conversion with known coordinates, SWA code fast path, point-in-polygon with real borough boundaries (Brixton Road→Lambeth, Borough High Street→Southwark, Streatham→Lambeth, Croydon town centre→Croydon), rejection of coordinates outside target area (Canary Wharf, Islington).
- **Classification (8 tests):** All traffic management types, emergency works, footway vs carriageway, unknown types.
- **Webhook (7 tests):** Health endpoint, valid notifications, irrelevant events, malformed body, unsigned message rejection, unknown SNS types, subscription confirmation signature bypass.
- **Notion schemas (3 tests):** Basic property mapping, missing fields, optional fields omitted.
- **Integration (4 tests):** Real boundary data loading, real coordinate matching.

---

## 14. Related Projects

- **lambeth-cyclists-claude** (`C:\Users\charl\ClaudeProjects\lambeth-cyclists-claude`): Email bot that monitors Gmail and writes to Notion. Uses the same stack (Python, notion-client, anthropic, Railway). Future enhancement: its agenda generation module could query the Roadworks Notion database from this project to include upcoming roadworks in meeting agendas.

---

## Appendix A: Useful Links

- Street Manager docs: https://department-for-transport-streetmanager.github.io/street-manager-docs/
- Street Manager open data: https://department-for-transport-streetmanager.github.io/street-manager-docs/open-data/
- Street Manager API notifications: https://department-for-transport-streetmanager.github.io/street-manager-docs/api-notifications/
- Street Manager helpdesk: https://streetmanager.atlassian.net/servicedesk/customer/portals
- Street Manager Python client: https://github.com/cogna-public/streetmanager
- D-TRO GitHub: https://github.com/department-for-transport-public/D-TRO
- D-TRO service: https://d-tro.dft.gov.uk
- ONS Open Geography Portal: https://geoportal.statistics.gov.uk/
- London Datastore boundaries: https://data.london.gov.uk/dataset/statistical-gis-boundary-files-london
- Chris Carlon's Street Works analysis (inspiration): https://www.ccarlon.dev/blog/street_works/
- Transport select committee report on street works: https://publications.parliament.uk/pa/cm5901/cmselect/cmtrans/522/report.html
