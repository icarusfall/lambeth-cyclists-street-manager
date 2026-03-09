"""FastAPI application — receives Street Manager SNS notifications and writes to Notion."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI

from src.config import settings
from src.geo.boundaries import load_borough_polygons
from src.geo.filter import GeoFilter
from src.notion.writer import NotionWriter
from src.pipeline import Pipeline
from src.street_manager.webhook import router as webhook_router, set_notification_handler

logger = logging.getLogger(__name__)

# Track app state for health endpoint
_app_state = {
    "started_at": None,
    "last_notification_at": None,
    "notifications_processed": 0,
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

        # Warm the Notion cache (loads existing permit refs to avoid duplicates)
        if settings.notion_api_key and settings.notion_roadworks_db_id:
            try:
                await notion_writer.warm_cache()
            except Exception:
                logger.exception("Failed to warm Notion cache — will query per item")
        else:
            logger.warning("Notion not configured — running in dry-run mode")

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

    except Exception as e:
        logger.exception("Startup error — app will serve health endpoint but not process notifications")
        _app_state["status"] = "degraded"
        _app_state["error"] = str(e)

    _app_state["started_at"] = datetime.now(timezone.utc).isoformat()

    # Start keep-alive self-ping to prevent Railway from sleeping the container.
    # Railway sleeps inactive containers, which would cause us to miss SNS notifications.
    ping_task = asyncio.create_task(_keep_alive())

    yield

    ping_task.cancel()
    logger.info("Shutting down")


async def _keep_alive():
    """Ping our own health endpoint every 5 minutes to prevent Railway sleep.

    Uses the public URL so Railway counts it as external traffic.
    Falls back to localhost if RAILWAY_PUBLIC_DOMAIN is not set.
    """
    public_domain = os.environ.get(
        "RAILWAY_PUBLIC_DOMAIN",
        "lambeth-cyclists-street-manager-production.up.railway.app",
    )
    url = f"https://{public_domain}/health"

    logger.info("Keep-alive will ping: %s", url)

    async with httpx.AsyncClient() as client:
        # Initial ping immediately to establish external traffic
        try:
            resp = await client.get(url, timeout=10)
            logger.info("Initial keep-alive ping: %s", resp.status_code)
        except Exception:
            pass

        while True:
            await asyncio.sleep(120)  # 2 minutes
            try:
                resp = await client.get(url, timeout=10)
                logger.debug("Keep-alive ping: %s", resp.status_code)
            except Exception:
                pass  # Non-critical — just a keep-alive


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
        "boroughs_monitored": len(settings.get_target_boroughs()),
        "error": _app_state["error"],
    }
