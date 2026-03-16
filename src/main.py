"""FastAPI application — receives Street Manager SNS notifications and writes to PostgreSQL."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from src.config import settings
from src.db.writer import DatabaseWriter
from src.geo.boundaries import load_borough_polygons
from src.geo.cycling_infrastructure import CyclingInfrastructureIndex
from src.geo.filter import GeoFilter
from src.pipeline import Pipeline
from src.street_manager.webhook import router as webhook_router, set_notification_handler
from src.dtro.pipeline import poll_traffic_orders
from src.laqn.pipeline import poll_air_quality
from src.tfl.pipeline import poll_disruptions

logger = logging.getLogger(__name__)

# Track app state for health endpoint
_app_state = {
    "started_at": None,
    "last_notification_at": None,
    "notifications_processed": 0,
    "last_disruption_poll": None,
    "disruptions_last_count": 0,
    "last_dtro_poll": None,
    "dtro_last_count": 0,
    "last_laqn_poll": None,
    "laqn_last_count": 0,
    "cid_features": 0,
    "status": "starting",
    "error": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting South London Street Works Monitor")

    db_writer = None
    poller_task = None
    dtro_poller_task = None
    laqn_poller_task = None

    try:
        # Load borough boundaries
        geojson_path = Path(__file__).parent.parent / "data" / "london_boroughs.geojson"
        borough_polygons = load_borough_polygons(str(geojson_path), settings.get_target_boroughs())

        # Load cycling infrastructure index (optional — files may not exist)
        data_dir = Path(__file__).parent.parent / "data"
        cid_index = None
        try:
            cid_index = CyclingInfrastructureIndex.load(data_dir)
            if cid_index.feature_count > 0:
                _app_state["cid_features"] = cid_index.feature_count
                logger.info("CID index loaded: %d cycling infrastructure features", cid_index.feature_count)
            else:
                logger.info("CID data files not found — running without cycling infrastructure index")
                cid_index = None
        except Exception:
            logger.exception("Failed to load CID index — running without it")

        # Initialise components
        geo_filter = GeoFilter(borough_polygons)

        # PostgreSQL writer
        if not settings.database_url:
            logger.warning("DATABASE_URL not set — running in dry-run mode")
            _app_state["status"] = "degraded"
            _app_state["error"] = "DATABASE_URL not configured"
            _app_state["started_at"] = datetime.now(timezone.utc).isoformat()
            yield
            return

        db_writer = DatabaseWriter(settings.database_url)
        await db_writer.connect()
        logger.info("PostgreSQL writer connected")

        pipeline = Pipeline(geo_filter, db_writer, cid_index=cid_index)

        # Wire up the SNS webhook to the pipeline
        async def handle_notification(notification: dict) -> None:
            _app_state["last_notification_at"] = datetime.now(timezone.utc).isoformat()
            _app_state["notifications_processed"] += 1
            await pipeline.process_notification(notification)

        set_notification_handler(handle_notification)

        _app_state["status"] = "ok"
        logger.info(
            "Ready — monitoring %d boroughs: %s",
            len(settings.get_target_boroughs()),
            ", ".join(settings.get_target_boroughs()),
        )

        # Start TfL disruptions poller
        poller_task = asyncio.create_task(
            _tfl_disruptions_poller(geo_filter, db_writer, cid_index)
        )
        logger.info("TfL disruptions poller started (daily at 09:00 UK time)")

        # Start D-TRO poller if configured
        if settings.dtro_api_key:
            dtro_poller_task = asyncio.create_task(
                _dtro_poller(db_writer, cid_index)
            )
            logger.info("D-TRO poller started (daily at 09:30 UK time)")
        else:
            logger.info("D-TRO poller not started — DTRO_API_KEY not set")

        # Start LAQN air quality poller
        laqn_poller_task = asyncio.create_task(_laqn_poller(db_writer))
        logger.info("LAQN air quality poller started (daily at 10:00 UK time)")

    except Exception as e:
        logger.exception("Startup error — app will serve health endpoint but not process notifications")
        _app_state["status"] = "degraded"
        _app_state["error"] = str(e)

    _app_state["started_at"] = datetime.now(timezone.utc).isoformat()

    yield

    if poller_task:
        poller_task.cancel()
    if dtro_poller_task:
        dtro_poller_task.cancel()
    if laqn_poller_task:
        laqn_poller_task.cancel()
    if db_writer:
        await db_writer.close()
    logger.info("Shutting down")


async def _tfl_disruptions_poller(
    geo_filter: GeoFilter,
    db_writer: DatabaseWriter,
    cid_index: CyclingInfrastructureIndex | None = None,
) -> None:
    """Poll TfL disruptions daily at 09:00 UK time."""
    uk_tz = ZoneInfo("Europe/London")

    # Initial poll on startup
    try:
        count = await poll_disruptions(geo_filter, db_writer, cid_index)
        _app_state["last_disruption_poll"] = datetime.now(timezone.utc).isoformat()
        _app_state["disruptions_last_count"] = count
    except Exception:
        logger.exception("TfL disruptions initial poll failed")

    while True:
        now = datetime.now(uk_tz)
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run = next_run + timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        logger.info("Next TfL disruptions poll at %s (in %.0f seconds)", next_run, wait_seconds)
        await asyncio.sleep(wait_seconds)

        try:
            count = await poll_disruptions(geo_filter, db_writer, cid_index)
            _app_state["last_disruption_poll"] = datetime.now(timezone.utc).isoformat()
            _app_state["disruptions_last_count"] = count
        except Exception:
            logger.exception("TfL disruptions poll failed")


async def _dtro_poller(
    db_writer: DatabaseWriter,
    cid_index: CyclingInfrastructureIndex | None = None,
) -> None:
    """Poll D-TRO API daily at 09:30 UK time."""
    uk_tz = ZoneInfo("Europe/London")

    # Initial poll on startup
    try:
        count = await poll_traffic_orders(db_writer, cid_index)
        _app_state["last_dtro_poll"] = datetime.now(timezone.utc).isoformat()
        _app_state["dtro_last_count"] = count
    except Exception:
        logger.exception("D-TRO initial poll failed")

    while True:
        now = datetime.now(uk_tz)
        next_run = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now >= next_run:
            next_run = next_run + timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        logger.info("Next D-TRO poll at %s (in %.0f seconds)", next_run, wait_seconds)
        await asyncio.sleep(wait_seconds)

        try:
            count = await poll_traffic_orders(db_writer, cid_index)
            _app_state["last_dtro_poll"] = datetime.now(timezone.utc).isoformat()
            _app_state["dtro_last_count"] = count
        except Exception:
            logger.exception("D-TRO poll failed")


async def _laqn_poller(db_writer: DatabaseWriter) -> None:
    """Poll LAQN air quality data daily at 10:00 UK time."""
    uk_tz = ZoneInfo("Europe/London")

    # Initial poll on startup
    try:
        count = await poll_air_quality(db_writer)
        _app_state["last_laqn_poll"] = datetime.now(timezone.utc).isoformat()
        _app_state["laqn_last_count"] = count
    except Exception:
        logger.exception("LAQN initial poll failed")

    while True:
        now = datetime.now(uk_tz)
        next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run = next_run + timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        logger.info("Next LAQN poll at %s (in %.0f seconds)", next_run, wait_seconds)
        await asyncio.sleep(wait_seconds)

        try:
            count = await poll_air_quality(db_writer)
            _app_state["last_laqn_poll"] = datetime.now(timezone.utc).isoformat()
            _app_state["laqn_last_count"] = count
        except Exception:
            logger.exception("LAQN poll failed")


app = FastAPI(
    title="South London Street Works Monitor",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount the SNS webhook router
app.include_router(webhook_router)


@app.get("/health")
async def health():
    """Health check endpoint for Railway monitoring."""
    return {
        "status": _app_state["status"],
        "started_at": _app_state["started_at"],
        "last_notification_at": _app_state["last_notification_at"],
        "notifications_processed": _app_state["notifications_processed"],
        "last_disruption_poll": _app_state["last_disruption_poll"],
        "disruptions_last_count": _app_state["disruptions_last_count"],
        "last_dtro_poll": _app_state["last_dtro_poll"],
        "dtro_last_count": _app_state["dtro_last_count"],
        "last_laqn_poll": _app_state["last_laqn_poll"],
        "laqn_last_count": _app_state["laqn_last_count"],
        "cid_features": _app_state["cid_features"],
        "boroughs_monitored": len(settings.get_target_boroughs()),
        "error": _app_state["error"],
    }
