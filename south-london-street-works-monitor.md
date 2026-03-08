# South London Street Works Monitor

## Architecture & Implementation Specification

**Project:** LCC South London Street Works Monitor
**Author:** Charlie (Lambeth Cyclists / London Cycling Campaign)
**Date:** March 2026
**Purpose:** Hand-off document for Claude Code implementation

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

**API type:** AWS SNS push notifications (primary) + REST polling endpoint (fallback).

**Registration:** Free open data account at https://www.manage-roadworks.service.gov.uk/open-data-onboarding

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

**Fallback polling endpoint:** `GET /works/updates` on the Event API, plus hourly CSV exports via the Data Export API. Use these for backfill/catch-up if SNS notifications are missed.

**Python client library:** https://github.com/cogna-public/streetmanager (may be useful, evaluate during implementation).

**API documentation:** https://department-for-transport-streetmanager.github.io/street-manager-docs/api-documentation/

### 2.2 D-TRO Service (DfT) — Digital Traffic Regulation Orders

**What:** Machine-readable versions of traffic regulation orders — speed limits, parking restrictions, one-way streets, road closures, weight limits, etc.

**API type:** REST API at https://d-tro.dft.gov.uk

**Registration:** Free at the URL above.

**Status:** Beta — the DfT planned to table regulations in Autumn 2025 making digital submission mandatory. Coverage may still be patchy. Check whether Lambeth and neighbouring authorities are actively publishing D-TROs.

**GitHub:** https://github.com/department-for-transport-public/D-TRO — contains data model docs, schema files, and example data for the current spec version (3.5.0).

**Implementation note:** D-TROs include geographic extents, so the same geo-filtering approach applies. Poll this API on a schedule (e.g. daily) rather than expecting push notifications.

**Priority:** Lower than Street Manager. Implement Street Manager first, add D-TRO support as a second phase. The API may require more exploration during implementation to understand the actual data format and query capabilities.

### 2.3 Borough Boundary Data — Geographic Filtering

**What:** GeoJSON polygon boundaries for London boroughs, used to determine whether a roadwork/order falls within our target area.

**Source:** London Datastore statistical GIS boundary files: https://data.london.gov.uk/dataset/statistical-gis-boundary-files-london

**Alternative sources:**
- OS Boundary-Line (free open data): https://www.ordnancesurvey.co.uk/products/boundary-line
- ONS Open Geography Portal: https://geoportal.statistics.gov.uk/
- Pre-made London borough GeoJSON on GitHub (various repos)

**Approach:** Download once, store in repo as a static GeoJSON file. No runtime API dependency on OS Data Hub or any external geo service. Load the target borough polygons at startup, union them into a single MultiPolygon using Shapely, and use it for point-in-polygon checks.

**Coordinate systems:** Street Manager uses British National Grid (EPSG:27700). Borough boundaries may be in WGS84 (EPSG:4326) or BNG depending on source. Either convert the borough boundaries to BNG at load time, or convert incoming coordinates to WGS84. Recommend converting incoming BNG coordinates to WGS84 using `pyproj`, since most boundary sources default to WGS84.

---

## 3. Architecture

### 3.1 High-Level Design

```
                    ┌─────────────────────┐
                    │   Street Manager    │
                    │   AWS SNS Topics    │
                    └────────┬────────────┘
                             │ HTTPS POST
                             ▼
┌──────────────────────────────────────────────┐
│          Python Daemon (Railway)              │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐   │
│  │ Flask/Fast-  │  │  Scheduled Jobs      │   │
│  │ API webhook  │  │  - D-TRO poll        │   │
│  │ receiver     │  │  - Cleanup/update    │   │
│  └──────┬───────┘  └──────────┬───────────┘   │
│         │                     │               │
│         ▼                     ▼               │
│  ┌──────────────────────────────────────┐     │
│  │        Geo-Filter Engine             │     │
│  │  1. SWA code check (fast path)       │     │
│  │  2. Point-in-polygon (geo path)      │     │
│  │  Borough boundaries loaded at start  │     │
│  └──────────────┬───────────────────────┘     │
│                 │                              │
│                 ▼                              │
│  ┌──────────────────────────────────────┐     │
│  │     Relevance Classifier             │     │
│  │  - Claude API for cycling relevance  │     │
│  │  - Traffic mgmt type categorisation  │     │
│  │  - Borough tagging                   │     │
│  └──────────────┬───────────────────────┘     │
│                 │                              │
│                 ▼                              │
│  ┌──────────────────────────────────────┐     │
│  │     Notion Writer                    │     │
│  │  - Upsert to Roadworks DB            │     │
│  │  - Upsert to Traffic Orders DB       │     │
│  │  - Update status of existing items   │     │
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
                    │  │ Roadworks DB  │  │
                    │  └───────────────┘  │
                    │  ┌───────────────┐  │
                    │  │ Traffic       │  │
                    │  │ Orders DB     │  │
                    │  └───────────────┘  │
                    └─────────────────────┘
```

### 3.2 Deployment

- **Platform:** Railway (existing infrastructure from Lambeth Cyclists email automation)
- **Runtime:** Python 3.11+
- **Process:** Single long-running process with both a web server (for SNS webhook) and scheduled tasks (for D-TRO polling, status updates)
- **Database:** None — Notion is the datastore. Use local state only for deduplication (in-memory set of recently-seen permit references, persisted to a small JSON file or Railway volume)
- **Domain:** The webhook endpoint needs a publicly accessible HTTPS URL. Railway provides this automatically.

### 3.3 Configuration (Environment Variables)

```
# Borough list (comma-separated borough names matching the boundary GeoJSON)
TARGET_BOROUGHS=Lambeth,Southwark,Wandsworth,Lewisham,Merton,Croydon,City of London,Westminster

# Known borough SWA codes for fast-path filtering
# (TfL SWA code is also needed for the geo-path)
BOROUGH_SWA_CODES=5660,5630,5690,5420,5510,5210

# Notion
NOTION_API_KEY=secret_xxx
NOTION_ROADWORKS_DB_ID=xxx
NOTION_TRAFFIC_ORDERS_DB_ID=xxx

# Anthropic (for cycling relevance classification)
ANTHROPIC_API_KEY=sk-ant-xxx

# Street Manager (if authenticated API access is used for backfill)
STREET_MANAGER_API_EMAIL=xxx
STREET_MANAGER_API_PASSWORD=xxx

# D-TRO
DTRO_API_KEY=xxx

# App
WEBHOOK_PATH=/webhook/street-manager
LOG_LEVEL=INFO
```

---

## 4. Geo-Filtering Logic

### 4.1 Two-Tier Filter

```python
# Pseudocode

def should_include(notification: dict) -> tuple[bool, str]:
    """
    Returns (include: bool, borough: str) for a Street Manager notification.
    """
    ha_swa = notification["object_data"]["highway_authority_swa_code"]

    # Fast path: if the highway authority IS one of our target boroughs
    if ha_swa in BOROUGH_SWA_CODES:
        borough = SWA_TO_BOROUGH[ha_swa]
        return True, borough

    # Geo path: for TfL roads, utility works, etc.
    coords_wkt = notification["object_data"].get("works_location_coordinates")
    if not coords_wkt:
        return False, ""

    point = parse_bng_wkt_to_wgs84(coords_wkt)

    # Check against each borough polygon individually (not the union)
    # so we can tag which borough it falls in
    for borough_name, polygon in BOROUGH_POLYGONS.items():
        if polygon.contains(point):
            return True, borough_name

    return False, ""
```

### 4.2 Coordinate Conversion

Street Manager uses BNG (EPSG:27700). Convert to WGS84 for matching against borough boundaries:

```python
from pyproj import Transformer
import re

transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

def parse_bng_wkt_to_wgs84(wkt: str) -> Point:
    """Parse 'POINT(527155.33 182227.95)' from BNG to WGS84 Point."""
    match = re.match(r"POINT\(([\d.]+)\s+([\d.]+)\)", wkt)
    easting, northing = float(match.group(1)), float(match.group(2))
    lon, lat = transformer.transform(easting, northing)
    return Point(lon, lat)
```

### 4.3 Borough Boundary Loading

```python
import json
from shapely.geometry import shape

def load_borough_polygons(geojson_path: str, target_boroughs: list[str]) -> dict:
    """Load target borough polygons from a London boroughs GeoJSON file."""
    with open(geojson_path) as f:
        data = json.load(f)

    polygons = {}
    for feature in data["features"]:
        # Property name varies by source — adapt as needed
        name = feature["properties"].get("name") or feature["properties"].get("NAME")
        if name in target_boroughs:
            polygons[name] = shape(feature["geometry"])

    missing = set(target_boroughs) - set(polygons.keys())
    if missing:
        raise ValueError(f"Boroughs not found in GeoJSON: {missing}")

    return polygons
```

---

## 5. Cycling Relevance Classifier

### 5.1 Rule-Based Pre-Filter

Before calling Claude API (which costs money), apply simple rules:

```python
HIGH_IMPACT_TRAFFIC_MGMT = {
    "road_closure",
    "lane_closure",
}

MEDIUM_IMPACT_TRAFFIC_MGMT = {
    "multi_way_signals",
    "two_way_signals",
    "convoy_working",
    "give_and_take",
}

LOW_IMPACT_TRAFFIC_MGMT = {
    "some_carriageway_restriction",
    "no_carriageway_restriction",
}

def quick_cycling_impact(notification: dict) -> str:
    """Returns 'high', 'medium', 'low', or 'minimal'."""
    tm = notification["object_data"].get("traffic_management_type_ref", "")
    cat = notification["object_data"].get("work_category_ref", "")
    loc = notification["object_data"].get("works_location_type", "")

    # Footway-only works are usually minimal impact for cycling
    if loc == "Footway" and tm in LOW_IMPACT_TRAFFIC_MGMT:
        return "minimal"

    if tm in HIGH_IMPACT_TRAFFIC_MGMT:
        return "high"
    elif tm in MEDIUM_IMPACT_TRAFFIC_MGMT:
        return "medium"
    elif cat in ("immediate_urgent", "immediate_emergency"):
        return "medium"  # Emergency works are unpredictable
    else:
        return "low"
```

### 5.2 Claude API Enrichment (Optional, for High/Medium Impact Only)

For roadworks classified as high or medium impact, optionally call Claude to generate a brief cycling-relevant summary:

```python
CLASSIFICATION_PROMPT = """You are helping a cycling advocacy group understand the impact of roadworks.

Given this roadwork notification, write a 1-2 sentence summary of how it affects people cycling in the area. Consider: whether the road is a common cycling route, whether alternative routes exist, whether the traffic management creates pinch points, and whether temporary arrangements are cycle-friendly.

Street: {street_name}, {area_name}
Borough: {borough}
Work type: {activity_type}
Traffic management: {traffic_management_type}
Duration: {proposed_start_date} to {proposed_end_date}
Category: {work_category}
Promoter: {promoter_organisation}

Reply with ONLY the summary, no preamble."""
```

**Cost control:** Only call this for high/medium impact works. That should be a small fraction of total notifications. Budget roughly 500 tokens per call, ~£0.001 per classification with Haiku.

---

## 6. Notion Database Schemas

### 6.1 Roadworks Database

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
| Actual End | Date | When work actually ended |
| Cycling Impact | Select | High / Medium / Low / Minimal |
| Cycling Summary | Rich text | Claude-generated summary (if applicable) |
| Activity Type | Rich text | e.g. "Utility repair and maintenance works" |
| TTRO Required | Checkbox | Whether a temporary traffic regulation order is required |
| Coordinates | Rich text | WGS84 lon,lat for reference |
| Last Updated | Date | When this record was last updated from Street Manager |
| Source Event | Rich text | Last event_type that triggered an update |

**Notion views to create manually:**

- **All Active** — filter: Work Status is not "Completed" and not "Cancelled", sort by Proposed Start descending
- **High Impact** — filter: Cycling Impact is "High", Work Status is not "Completed"
- **By Borough** — grouped by Borough, filtered to active works
- **Lambeth Only** — filter: Borough is "Lambeth"
- **Southwark Only** — filter: Borough is "Southwark"
- (etc. for each borough)
- **Road Closures** — filter: Traffic Management is "Road closure", Work Status is not "Completed"
- **This Week** — filter: Proposed Start is within this week

### 6.2 Traffic Orders Database (Phase 2 — D-TRO)

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

### Phase 1: Street Manager Integration (MVP)

1. **Project setup**
   - Python project with pyproject.toml or requirements.txt
   - Dependencies: `fastapi`, `uvicorn`, `httpx`, `shapely`, `pyproj`, `notion-client`, `anthropic`, `schedule` (or `apscheduler`)
   - Environment variable configuration via `pydantic-settings` or similar

2. **Borough boundary loader**
   - Download London boroughs GeoJSON (include in repo as `data/london_boroughs.geojson`)
   - Load and filter to target boroughs at startup
   - Test with known coordinates (e.g. Brixton Road should be in Lambeth)

3. **SNS webhook receiver**
   - FastAPI app with a POST endpoint at `/webhook/street-manager`
   - Handle SNS subscription confirmation (respond to SubscribeURL)
   - Handle SNS notification messages
   - Parse the nested JSON message body
   - Pass to filter pipeline

4. **Geo-filter pipeline**
   - Two-tier filter as described in Section 4
   - SWA code lookup table for target boroughs
   - BNG to WGS84 coordinate conversion
   - Point-in-polygon check against borough boundaries

5. **Deduplication**
   - Track seen `permit_reference_number` + `version` pairs
   - On update events, update existing Notion records rather than creating duplicates
   - Store mapping of permit_reference → Notion page ID (persist to JSON file or Railway volume)

6. **Notion writer**
   - Create/update pages in the Roadworks database
   - Map notification fields to Notion properties
   - Handle the title field (combine street_name + area_name)
   - Use permit_reference as the dedup key

7. **Cycling impact classifier**
   - Rule-based quick classification
   - Optional Claude API enrichment for high/medium items

8. **Deployment to Railway**
   - Dockerfile or nixpacks config
   - Environment variables
   - Health check endpoint
   - Logging to stdout

### Phase 2: D-TRO Integration

1. Explore the D-TRO API at https://d-tro.dft.gov.uk
2. Understand query capabilities and data format
3. Implement scheduled polling (daily)
4. Geo-filter D-TRO records against borough boundaries
5. Write to Traffic Orders Notion database
6. Add Claude classification for cycling relevance of traffic orders

### Phase 3: Enhancements

- **USRN enrichment:** Build a lookup of key cycling routes by USRN, flag works on these routes as automatically high-priority
- **Historical analysis:** Aggregate data over time to identify most-disrupted roads per borough (à la Chris Carlon's analysis)
- **Notification emails:** Send weekly digest or instant alerts for high-impact works to borough group mailing lists
- **Web dashboard:** Simple public page showing active high-impact works on a map (could be a static site on Vercel)

---

## 8. Key Technical Decisions

### Why SNS push rather than polling?

Street Manager's open data service uses AWS SNS for near-real-time notifications. This is better than polling because you get updates within minutes rather than hours, and you don't need to manage pagination or track what you've already seen. The downside is you need a publicly accessible HTTPS endpoint, but Railway provides this.

### Why not use OS Data Hub?

The OS Data Hub would add a runtime API dependency, rate limits, and an API key to manage. Since we only need borough boundary polygons (which are static data), downloading them once from the London Datastore or OS Boundary-Line is simpler and more reliable.

### Why Notion rather than a database?

Notion is already the Lambeth Cyclists workspace. The whole point is to put this data where the group already works. Notion's filtering and view capabilities are good enough for the use case, and non-technical group members can use it without any training. If performance becomes an issue (unlikely at borough-level volumes), we could add a PostgreSQL layer later.

### Why Claude for classification?

A simple rule-based classifier handles most cases, but some works benefit from contextual understanding — e.g. knowing that a "minor" work with "some carriageway restriction" on a narrow one-lane street is actually high impact for cycling, or that a road closure on a quiet residential street matters less than one on a main cycling corridor. Claude can provide this nuance. But it's optional and only used for high/medium impact works to control costs.

### Coordinate system handling

Street Manager uses British National Grid (EPSG:27700) throughout. Most publicly available borough boundary data is in WGS84 (EPSG:4326). Rather than converting boundaries to BNG, convert incoming coordinates to WGS84 using pyproj — this is a well-understood, one-line transformation and means our stored coordinates are in the more universally useful WGS84 format.

---

## 9. Registration Steps (Manual, Before Implementation)

These must be done by Charlie before the daemon can be deployed:

1. **Street Manager Open Data:** Register at https://www.manage-roadworks.service.gov.uk/open-data-onboarding — provide the Railway webhook URL once the app is deployed
2. **D-TRO Service:** Register at https://d-tro.dft.gov.uk — explore available data for London boroughs
3. **Notion Integration:** Create a new integration at https://www.notion.so/my-integrations — give it access to the Lambeth Cyclists workspace. Create the two databases (Roadworks, Traffic Orders) with the schemas above and share them with the integration.
4. **Anthropic API Key:** Use existing key from Lambeth Cyclists infrastructure (or the shared AI Club key if applicable)

---

## 10. SWA Code Reference

Borough SWA codes for fast-path filtering (verify these — they may need updating):

| Borough | SWA Code (approx) |
|---------|-------------------|
| Lambeth | 5540 |
| Southwark | 5630 |
| Wandsworth | 5690 |
| Lewisham | 5420 |
| Merton | 5510 |
| Croydon | 5210 |
| City of London | 5110 |
| Westminster | 5990 |
| Transport for London | 0999 (verify) |

**Important:** These codes should be verified against the Street Manager lookup API or registration data before going live. The lookup endpoint is available in the Street Manager API.

---

## 11. Error Handling & Resilience

- **SNS delivery failures:** AWS SNS retries up to 20 times over approximately one hour. If the webhook is down longer than that, use the polling endpoint (`GET /works/updates`) to backfill missed events.
- **Notion API rate limits:** The Notion API has rate limits (currently 3 requests/second). Implement exponential backoff. Batch updates where possible.
- **Malformed notifications:** Log and skip any notifications that can't be parsed. Don't crash the process.
- **Startup recovery:** On restart, check the polling endpoint for any events missed since the last known event timestamp (store this in a local file).
- **Health check:** Expose a `GET /health` endpoint that returns 200 if the process is running. Railway can use this for monitoring.

---

## 12. Project Structure

```
south-london-street-works-monitor/
├── README.md
├── pyproject.toml
├── Dockerfile
├── .env.example
├── data/
│   └── london_boroughs.geojson      # Static borough boundary data
├── src/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app + scheduled jobs
│   ├── config.py                     # Pydantic settings from env vars
│   ├── geo/
│   │   ├── __init__.py
│   │   ├── boundaries.py             # Borough polygon loading
│   │   └── filter.py                 # Two-tier geo-filter
│   ├── street_manager/
│   │   ├── __init__.py
│   │   ├── webhook.py                # SNS webhook handler
│   │   ├── parser.py                 # Notification parsing
│   │   └── poller.py                 # Fallback polling endpoint
│   ├── dtro/
│   │   ├── __init__.py
│   │   └── client.py                 # D-TRO API client (Phase 2)
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── rules.py                  # Rule-based impact classification
│   │   └── claude.py                 # Claude API enrichment
│   ├── notion/
│   │   ├── __init__.py
│   │   ├── writer.py                 # Notion database operations
│   │   └── schemas.py                # Property mappings
│   └── state/
│       ├── __init__.py
│       └── dedup.py                  # Deduplication + permit→page ID mapping
├── tests/
│   ├── test_geo_filter.py
│   ├── test_parser.py
│   ├── test_classifier.py
│   └── fixtures/
│       ├── sample_permit_notification.json
│       └── sample_activity_notification.json
└── scripts/
    └── backfill.py                   # One-off script to backfill from polling endpoint
```

---

## 13. Testing Strategy

- **Unit tests for geo-filtering:** Known coordinates on Brixton Road (TfL/TLRN, should match Lambeth), Streatham High Road (should match Lambeth), Borough High Street (should match Southwark), Wandsworth Bridge Road (should match Wandsworth). Also test coordinates outside all target boroughs (should be rejected).
- **Unit tests for notification parsing:** Use sample payloads from Street Manager documentation.
- **Unit tests for classification rules:** Various traffic management types and work categories.
- **Integration test with Notion:** Create a test database, write a record, verify fields, delete it.
- **End-to-end:** Simulate an SNS notification POST to the webhook, verify it flows through to a Notion record.

---

## Appendix A: Useful Links

- Street Manager docs: https://department-for-transport-streetmanager.github.io/street-manager-docs/
- Street Manager open data: https://department-for-transport-streetmanager.github.io/street-manager-docs/open-data/
- Street Manager API notifications: https://department-for-transport-streetmanager.github.io/street-manager-docs/api-notifications/
- Street Manager Python client: https://github.com/cogna-public/streetmanager
- D-TRO GitHub: https://github.com/department-for-transport-public/D-TRO
- D-TRO service: https://d-tro.dft.gov.uk
- London Datastore boundaries: https://data.london.gov.uk/dataset/statistical-gis-boundary-files-london
- OS Boundary-Line: https://www.ordnancesurvey.co.uk/products/boundary-line
- Chris Carlon's Street Works analysis (inspiration): https://www.ccarlon.dev/blog/street_works/
- Transport select committee report on street works: https://publications.parliament.uk/pa/cm5901/cmselect/cmtrans/522/report.html
