"""STATS19 cycling collision data importer.

Downloads DfT road casualty statistics CSVs, filters to cyclist casualties
in target boroughs, and writes to a Notion database.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field

import httpx
from shapely.geometry import Point

from src.geo.filter import GeoFilter

logger = logging.getLogger(__name__)

# Base URL for DfT road casualty statistics CSVs
_BASE_URL = "https://data.dft.gov.uk/road-accidents-safety-data"

# STATS19 coded value lookups
SEVERITY_LABELS = {1: "Fatal", 2: "Serious", 3: "Slight"}

VEHICLE_TYPE_LABELS = {
    1: "Pedal cycle",
    2: "Motorcycle",
    3: "Motorcycle",
    4: "Motorcycle",
    5: "Motorcycle",
    8: "Taxi",
    9: "Car",
    10: "Minibus",
    11: "Bus/Coach",
    16: "Horse",
    17: "Agricultural vehicle",
    18: "Tram",
    19: "Van",
    20: "HGV",
    21: "HGV",
    22: "Mobility scooter",
    23: "Electric motorcycle",
    90: "Other",
    97: "Motorcycle",
    98: "Goods vehicle",
    99: "Unknown",
}

LIGHT_CONDITIONS_LABELS = {
    1: "Daylight",
    4: "Darkness - lights lit",
    5: "Darkness - lights unlit",
    6: "Darkness - no lighting",
    7: "Darkness - lighting unknown",
}

WEATHER_LABELS = {
    1: "Fine",
    2: "Rain",
    3: "Snow",
    4: "Fine + high winds",
    5: "Rain + high winds",
    6: "Snow + high winds",
    7: "Fog or mist",
    8: "Other",
    9: "Unknown",
}

ROAD_SURFACE_LABELS = {
    1: "Dry",
    2: "Wet",
    3: "Snow",
    4: "Frost or ice",
    5: "Flood",
    6: "Oil or diesel",
    7: "Mud",
    9: "Unknown",
}

JUNCTION_DETAIL_LABELS = {
    0: "Not at junction",
    13: "T or staggered junction",
    16: "Crossroads",
    17: "More than four arms",
    18: "Private drive or entrance",
    99: "Unknown",
}


def _safe_int(value: str, default: int = -1) -> int:
    """Parse an integer from a CSV value, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: str) -> float | None:
    """Parse a float from a CSV value, returning None on failure."""
    try:
        v = float(value)
        return v if v != 0.0 else None
    except (ValueError, TypeError):
        return None


@dataclass
class CyclistCollision:
    """A collision involving at least one cyclist, ready for Notion."""

    collision_index: str
    date: str
    time: str
    latitude: float
    longitude: float
    borough: str
    collision_severity: str
    num_cyclist_casualties: int
    worst_cyclist_severity: str
    other_vehicles: list[str]
    road_name: str
    speed_limit: int
    junction_detail: str
    light_conditions: str
    weather: str
    road_surface: str
    data_year: str


async def download_csv(url: str) -> list[dict]:
    """Download a CSV file and return rows as dicts."""
    logger.info("Downloading %s", url)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    text = resp.text
    # Handle BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    logger.info("Downloaded %d rows from %s", len(rows), url.split("/")[-1])
    return rows


def _build_collision_urls(year: int) -> tuple[str, str, str]:
    """Build download URLs for a specific year's STATS19 data."""
    return (
        f"{_BASE_URL}/dft-road-casualty-statistics-collision-{year}.csv",
        f"{_BASE_URL}/dft-road-casualty-statistics-casualty-{year}.csv",
        f"{_BASE_URL}/dft-road-casualty-statistics-vehicle-{year}.csv",
    )


def _build_last5_urls() -> tuple[str, str, str]:
    """Build download URLs for the last 5 years combined data."""
    return (
        f"{_BASE_URL}/dft-road-casualty-statistics-collision-last-5-years.csv",
        f"{_BASE_URL}/dft-road-casualty-statistics-casualty-last-5-years.csv",
        f"{_BASE_URL}/dft-road-casualty-statistics-vehicle-last-5-years.csv",
    )


def filter_cycling_collisions(
    collisions: list[dict],
    casualties: list[dict],
    vehicles: list[dict],
    geo_filter: GeoFilter,
) -> list[CyclistCollision]:
    """Filter STATS19 data to cyclist collisions in target boroughs.

    Args:
        collisions: Rows from the collision CSV.
        casualties: Rows from the casualty CSV.
        vehicles: Rows from the vehicle CSV.
        geo_filter: GeoFilter for borough containment checks.

    Returns:
        List of CyclistCollision records ready for Notion.
    """
    # Step 1: Find all collision_index values with cyclist casualties
    cyclist_casualties: dict[str, list[dict]] = {}
    for cas in casualties:
        if _safe_int(cas.get("casualty_type", "")) == 1:  # Pedal cyclist
            idx = cas.get("collision_index", "")
            if idx:
                cyclist_casualties.setdefault(idx, []).append(cas)

    logger.info(
        "Found %d collisions with cyclist casualties (from %d total casualties)",
        len(cyclist_casualties),
        len(casualties),
    )

    # Step 2: Index vehicles by collision_index
    vehicles_by_collision: dict[str, list[dict]] = {}
    for veh in vehicles:
        idx = veh.get("collision_index", "")
        if idx:
            vehicles_by_collision.setdefault(idx, []).append(veh)

    # Step 3: Filter collisions to those with cyclists AND in target boroughs
    results = []
    geo_hits = 0
    for col in collisions:
        idx = col.get("collision_index", "")
        if idx not in cyclist_casualties:
            continue

        lat = _safe_float(col.get("latitude", ""))
        lon = _safe_float(col.get("longitude", ""))
        if lat is None or lon is None:
            continue

        # Geo-filter using WGS84 coordinates
        point = Point(lon, lat)
        in_borough, borough = geo_filter.check_wgs84_point(point)
        if not in_borough:
            continue

        geo_hits += 1

        # Build the record
        cas_list = cyclist_casualties[idx]
        severity_codes = [_safe_int(c.get("casualty_severity", "")) for c in cas_list]
        worst_severity = min(s for s in severity_codes if s > 0)  # 1=Fatal is worst

        # Other vehicles (exclude pedal cycles)
        other_vehs = []
        for veh in vehicles_by_collision.get(idx, []):
            vtype = _safe_int(veh.get("vehicle_type", ""))
            if vtype != 1:  # Not a pedal cycle
                label = VEHICLE_TYPE_LABELS.get(vtype, f"Unknown ({vtype})")
                if label not in other_vehs:
                    other_vehs.append(label)

        # Build road name from road class + number
        road_class = col.get("first_road_class", "")
        road_number = col.get("first_road_number", "")
        road_name = ""
        if road_class and road_number and road_number != "0":
            class_prefix = {"1": "M", "2": "A(M)", "3": "A", "4": "B", "5": "C", "6": "U"}
            prefix = class_prefix.get(road_class, "")
            road_name = f"{prefix}{road_number}" if prefix else ""

        results.append(CyclistCollision(
            collision_index=idx,
            date=col.get("date", ""),
            time=col.get("time", ""),
            latitude=lat,
            longitude=lon,
            borough=borough,
            collision_severity=SEVERITY_LABELS.get(
                _safe_int(col.get("collision_severity", "")), "Unknown"
            ),
            num_cyclist_casualties=len(cas_list),
            worst_cyclist_severity=SEVERITY_LABELS.get(worst_severity, "Unknown"),
            other_vehicles=other_vehs,
            road_name=road_name,
            speed_limit=_safe_int(col.get("speed_limit", ""), 0),
            junction_detail=JUNCTION_DETAIL_LABELS.get(
                _safe_int(col.get("junction_detail", "")), "Unknown"
            ),
            light_conditions=LIGHT_CONDITIONS_LABELS.get(
                _safe_int(col.get("light_conditions", "")), "Unknown"
            ),
            weather=WEATHER_LABELS.get(
                _safe_int(col.get("weather_conditions", "")), "Unknown"
            ),
            road_surface=ROAD_SURFACE_LABELS.get(
                _safe_int(col.get("road_surface_conditions", "")), "Unknown"
            ),
            data_year=col.get("collision_year", str(idx[:4]) if len(idx) >= 4 else ""),
        ))

    logger.info(
        "Filtered to %d cyclist collisions in target boroughs (from %d with cyclists)",
        len(results),
        len(cyclist_casualties),
    )
    return results


async def import_collisions(
    geo_filter: GeoFilter,
    year: int | None = None,
    use_last5: bool = False,
) -> list[CyclistCollision]:
    """Download STATS19 data and return filtered cyclist collisions.

    Args:
        geo_filter: GeoFilter for borough containment checks.
        year: Specific year to download (e.g. 2024).
        use_last5: If True, download the last 5 years combined file.

    Returns:
        List of CyclistCollision records.
    """
    if use_last5:
        col_url, cas_url, veh_url = _build_last5_urls()
    elif year:
        col_url, cas_url, veh_url = _build_collision_urls(year)
    else:
        raise ValueError("Either year or use_last5 must be specified")

    collisions = await download_csv(col_url)
    casualties = await download_csv(cas_url)
    vehicles = await download_csv(veh_url)

    return filter_cycling_collisions(collisions, casualties, vehicles, geo_filter)
