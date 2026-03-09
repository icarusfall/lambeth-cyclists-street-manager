"""FastAPI application — receives Street Manager SNS notifications and writes to Notion."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI

from src.config import settings
from src.geo.boundaries import load_borough_polygons
from src.geo.filter import GeoFilter
from src.notion.writer import NotionWriter
from src.pipeline import Pipeline
from src.street_manager.webhook import router as webhook_router, set_notification_handler
from src.tfl.pipeline import poll_disruptions

logger = logging.getLogger(__name__)

# Track app state for health endpoint
_app_state = {
    "started_at": None,
    "last_notification_at": None,
    "notifications_processed": 0,
    "last_disruption_poll": None,
    "disruptions_last_count": 0,
    "status": "starting",
    "error": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting South London Street Works Monitor")

    try:
        # Load borough boundaries
        geojson_path = Path(__file__).parent.parent / "data" / "london_boroughs.geojson"
        borough_polygons = load_borough_polygons(str(geojson_path), settings.get_target_boroughs())

        # Initialise components
        geo_filter = GeoFilter(borough_polygons)
        notion_writer = NotionWriter()
        pipeline = Pipeline(geo_filter, notion_writer)

        # Warm the Notion caches (loads existing refs to avoid duplicates)
        if settings.notion_api_key and settings.notion_roadworks_db_id:
            try:
                await notion_writer.warm_cache()
            except Exception:
                logger.exception("Failed to warm Notion cache — will query per item")
        else:
            logger.warning("Notion not configured — running in dry-run mode")

        if settings.notion_api_key and settings.notion_disruptions_db_id:
            try:
                await notion_writer.warm_disruptions_cache()
            except Exception:
                logger.exception("Failed to warm disruptions cache")

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

        # Start TfL disruptions poller if configured
        poller_task = None
        if settings.notion_disruptions_db_id:
            poller_task = asyncio.create_task(
                _tfl_disruptions_poller(geo_filter, notion_writer)
            )
            logger.info(
                "TfL disruptions poller started (every %ds)",
                settings.tfl_poll_interval_seconds,
            )
        else:
            logger.info("TfL disruptions poller not started — NOTION_DISRUPTIONS_DB_ID not set")

    except Exception as e:
        logger.exception("Startup error — app will serve health endpoint but not process notifications")
        _app_state["status"] = "degraded"
        _app_state["error"] = str(e)
        poller_task = None

    _app_state["started_at"] = datetime.now(timezone.utc).isoformat()

    yield

    if poller_task:
        poller_task.cancel()
    logger.info("Shutting down")


async def _tfl_disruptions_poller(
    geo_filter: GeoFilter, notion_writer: NotionWriter
) -> None:
    """Poll TfL disruptions on a recurring interval."""
    interval = settings.tfl_poll_interval_seconds
    while True:
        try:
            count = await poll_disruptions(geo_filter, notion_writer)
            _app_state["last_disruption_poll"] = datetime.now(timezone.utc).isoformat()
            _app_state["disruptions_last_count"] = count
        except Exception:
            logger.exception("TfL disruptions poll failed")
        await asyncio.sleep(interval)


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
        "boroughs_monitored": len(settings.get_target_boroughs()),
        "error": _app_state["error"],
    }
