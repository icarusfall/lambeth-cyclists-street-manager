# LCC South London — Data Dictionary

**Purpose:** Reference document for downstream projects (dashboards, visualisations, map overlays) that consume data produced by the Street Works Monitor pipeline.

**Data store:** Notion (via Notion API v2022-06-28)
**Pipeline repo:** https://github.com/icarusfall/lambeth-cyclists-street-manager
**Live endpoint:** https://lambeth-cyclists-street-manager-production.up.railway.app

---

## Coverage

All databases cover **8 south/central London boroughs:**
Lambeth, Southwark, Wandsworth, Lewisham, Merton, Croydon, City of London, Westminster

---

## 1. Roadworks (Street Manager Permits & Activities)

**Notion database ID env var:** `NOTION_ROADWORKS_DB_ID`
**Update cadence:** Real-time (SNS push from DfT Street Manager)
**Dedup key:** Permit Reference
**Approximate volume:** ~3,800 records (and growing daily)

### Fields

| Field | Notion Type | Description | Example |
|-------|-------------|-------------|---------|
| Name | title | Street name and area | "Brixton Road, Lambeth" |
| Permit Reference | rich_text | Unique DfT permit/activity ref | "XX058005100648583-01" |
| Work Reference | rich_text | Parent work reference | "XX058005100648583" |
| Borough | select | Geo-filtered borough | "Lambeth" |
| Highway Authority | rich_text | Responsible highway authority | "Transport for London" |
| Street Name | rich_text | Street where works take place | "Brixton Road" |
| Area | rich_text | Area/town name | "Lambeth" |
| USRN | rich_text | Unique Street Reference Number | "20500753" |
| Promoter | rich_text | Organisation doing the works | "Thames Water Utilities Ltd" |
| Work Category | select | Scale of works | Major, Standard, Minor, Immediate Urgent, Immediate Emergency |
| Traffic Management | select | Type of traffic control | Road closure, Lane closure, Multi-way signals, Two-way signals, Convoy working, Give and take, Some carriageway restriction, No carriageway restriction |
| Work Status | select | Current status | Planned, In progress, Completed, Cancelled, Unattributable, Historical, Non-notifiable, Section 81 |
| Proposed Start | date | Planned start date | 2026-03-15 |
| Proposed End | date | Planned end date | 2026-03-20 |
| Actual Start | date | When works actually started | 2026-03-15 |
| Cycling Impact | select | Pipeline-classified impact | High, Medium, Low, Minimal |
| Activity Type | rich_text | Type of activity (for non-permit works) | "Remedial works" |
| TTRO Required | checkbox | Temporary Traffic Regulation Order needed | true/false |
| Last Updated | date | When this record was last written | ISO datetime |
| Source Event | rich_text | SNS event that triggered this update | "PERMIT_SUBMITTED", "WORK_START" |
| Cycling Summary | rich_text | Claude-generated plain-English summary | "Road closure on a busy cycle commute corridor..." |
| Coordinates | rich_text | WGS84 point (converted from BNG) | "-0.1148,51.4613" (lon,lat) |
| Nearby Cycling Infrastructure | rich_text | Closest CID asset within 50m | "Cycleway 7 — Segregated cycle track (12m)" |

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

## 2. TfL Disruptions

**Notion database ID env var:** `NOTION_DISRUPTIONS_DB_ID`
**Update cadence:** Daily poll at 09:00 UK time
**Dedup key:** TfL Disruption ID
**Approximate volume:** ~70 active at any time

### Fields

| Field | Notion Type | Description | Example |
|-------|-------------|-------------|---------|
| Name | title | Location and category | "Westminster Bridge Road — Works" |
| TfL Disruption ID | rich_text | TfL's unique disruption ID | "TIMS-225683" |
| Borough | select | Geo-filtered borough | "Southwark" |
| Category | select | Type of disruption | Works, Collisions, Hazards, Network delays, Asset issues, Breakdowns, Planned events |
| Sub-Category | rich_text | More specific category | "Roadworks" |
| Status | select | Current state | Active, Scheduled, Resolved |
| Severity | rich_text | TfL severity level | "Serious", "Moderate", "Minimal" |
| Location | rich_text | Human-readable location | "Westminster Bridge Road both directions" |
| Corridors | rich_text | Affected TfL corridors | "TLRN Road Network" |
| Start Time | date | When disruption starts/started | ISO datetime |
| End Time | date | When disruption ends/ended | ISO datetime |
| Description | rich_text | TfL's description (max 2000 chars) | "Temporary traffic signals..." |
| Cycling Impact | select | Pipeline-classified impact | High, Medium, Low, Minimal |
| Last Updated | date | When this record was last written | ISO datetime |
| Cycling Summary | rich_text | Claude-generated summary (high/medium only) | "Lane closure on key cycle commute route..." |
| Coordinates | rich_text | WGS84 centroid of disruption | "-0.1065,51.4982" (lon,lat) |
| Nearby Cycling Infrastructure | rich_text | Closest CID asset within 50m | "Mandatory cycle lane (23m)" |

### Lifecycle

Disruptions that disappear from the TfL API are automatically marked as **Resolved** in Notion. The poller compares active IDs from the API against the cache and updates missing ones.

---

## 3. Cycling Collisions (STATS19)

**Notion database ID env var:** `NOTION_COLLISIONS_DB_ID`
**Update cadence:** One-off annual import (DfT publishes yearly)
**Dedup key:** Collision Reference
**Data source:** DfT STATS19 open data (collisions, casualties, vehicles CSVs)

### Fields

| Field | Notion Type | Description | Example |
|-------|-------------|-------------|---------|
| Name | title | Road and date | "A23 — 2023-07-15" |
| Collision Reference | rich_text | STATS19 collision index | "2023010012345" |
| Borough | select | Geo-filtered borough | "Croydon" |
| Date | date | Date of collision | 2023-07-15 |
| Time | rich_text | Time of collision | "08:30" |
| Severity | select | Overall collision severity | Fatal, Serious, Slight |
| Number of Cyclists Hurt | number | Count of cyclist casualties | 1 |
| Worst Cyclist Severity | select | Worst outcome for any cyclist | Fatal, Serious, Slight |
| Other Vehicles | rich_text | Non-cycle vehicles involved | "Car, HGV" |
| Road Name | rich_text | Road class + number | "A23", "B234" |
| Speed Limit | number | Speed limit at location (mph) | 30 |
| Junction Detail | select | Junction type | Not at junction, T or staggered, Crossroads, More than four arms, Private drive, Unknown |
| Light Conditions | select | Lighting at time of collision | Daylight, Darkness - lights lit, Darkness - lights unlit, etc. |
| Weather | select | Weather conditions | Fine, Rain, Snow, Fog or mist, etc. |
| Road Surface | select | Surface condition | Dry, Wet, Snow, Frost or ice, Flood, etc. |
| Coordinates | rich_text | WGS84 point | "-0.0876,51.3721" (lon,lat) |
| Data Year | rich_text | Year of STATS19 dataset | "2023" |

### Notes

- Only collisions involving at least one **pedal cyclist casualty** are imported
- Vehicle type "Pedal cycle" is excluded from the "Other Vehicles" field (it's implicit)
- Historical data — not updated in real time

---

## 4. Traffic Orders (D-TRO)

**Notion database ID env var:** `NOTION_TRAFFIC_ORDERS_DB_ID`
**Update cadence:** Daily poll at 09:30 UK time
**Dedup key:** D-TRO ID
**Data source:** DfT D-TRO API (https://dtro.dft.gov.uk/v1)

### Fields

| Field | Notion Type | Description | Example |
|-------|-------------|-------------|---------|
| Name | title | TRO name | "Lambeth (Brixton Road) (No. 1) Traffic Order 2026" |
| D-TRO ID | rich_text | DfT unique identifier | "d268d055-66c1-40cd-ab07-31237c6974d1" |
| D-TRO Reference | rich_text | Local authority reference | "2026/TRO/0042" |
| Borough | select | Mapped from SWA code | "Lambeth" |
| Regulation Type | multi_select | What the order regulates | cycleLane, miscRoadClosure, speedLimit, kerbsideNoWaiting, etc. |
| Location Description | rich_text | Where it applies | "Brixton Road from junction with..." |
| Street Name | rich_text | Affected streets | "Brixton Road, Acre Lane" |
| Made Date | date | When order was made | 2026-03-01 |
| Effective Date | date | When order comes into force | 2026-03-15 |
| End Date | date | Expiry (if temporary) | 2026-06-15 |
| Authority | rich_text | Traffic regulation authority | "London Borough of Lambeth" |
| Action Type | select | What's happening | New, Revocation |
| Cycling Impact | select | Pipeline-classified impact | Positive, Negative, Neutral, Needs Review |
| Schema Version | rich_text | D-TRO schema version | "3.3.1" |
| Last Updated | date | When this record was last written | ISO datetime |
| Cycling Summary | rich_text | Claude-generated summary (Negative/Needs Review only) | "Revocation of existing cycle lane on..." |
| Coordinates | rich_text | WGS84 point (converted from BNG linestring midpoint) | "-0.1148,51.4613" (lon,lat) |
| Nearby Cycling Infrastructure | rich_text | Closest CID asset within 50m | "Advisory cycle lane (8m)" |

### Cycling Impact classification (different from roadworks)

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

## 5. Cycling Infrastructure Reference Layer (not a Notion database)

This is a **spatial index loaded at runtime**, not stored in Notion. It enriches the other databases via the "Nearby Cycling Infrastructure" field.

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

## 6. Coordinate Format

All `Coordinates` fields use the format `"lon,lat"` in **WGS84** (EPSG:4326).

Example: `"-0.1148,51.4613"` = 0.1148 degrees West, 51.4613 degrees North (Brixton Road area)

**Note:** longitude comes first, matching GeoJSON convention. This is the opposite of Google Maps URL format (which uses lat,lon).

Street Manager data arrives in **British National Grid (EPSG:27700)** and is converted to WGS84 by the pipeline using pyproj. TfL and STATS19 data is already in WGS84.

---

## 7. Notion API Access

**Authentication:** Bearer token via `NOTION_API_KEY` environment variable
**API version:** 2022-06-28 (via notion-client v2.2.1)
**Rate limits:** Notion API allows 3 requests/second average

### Querying databases

```
POST https://api.notion.com/v1/databases/{database_id}/query
Headers:
  Authorization: Bearer {NOTION_API_KEY}
  Notion-Version: 2022-06-28
  Content-Type: application/json
```

Pagination: results come in pages of 100. Follow `next_cursor` until `has_more` is false.

### Database IDs

These are set as Railway environment variables. To find them, open the Notion database in a browser — the ID is the 32-character hex string in the URL before the `?v=` parameter.

---

## 8. Data Freshness & Pipeline Schedule

| Database | Update Mechanism | Frequency | Typical Latency |
|----------|-----------------|-----------|-----------------|
| Roadworks | SNS webhook (push) | Real-time | Seconds after DfT publishes |
| TfL Disruptions | HTTP poll | Daily at 09:00 UK | Up to 24 hours |
| STATS19 Collisions | Manual import | Annual | Months (DfT publishes ~6 months after year end) |
| Traffic Orders | HTTP poll | Daily at 09:30 UK | Up to 24 hours |

---

## 9. Other Notion Workspace Data (not managed by this pipeline)

The LCC South London Notion workspace also contains manually curated tables that are relevant for a visualisation/dashboard project:

- **Ward councillor research** — political data for the May 2026 local elections
- Other campaign tables maintained by borough group volunteers

These tables are not populated by this pipeline but could be read by a downstream visualisation project via the same Notion API key, provided the integration has been shared with those databases.
