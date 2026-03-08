import logging
from pydantic_settings import BaseSettings


# SWA codes for target boroughs — used for fast-path geo-filtering.
# These identify the highway authority responsible for a road.
# Verify against Street Manager before going live.
BOROUGH_SWA_CODES: dict[str, str] = {
    "5540": "Lambeth",
    "5630": "Southwark",
    "5690": "Wandsworth",
    "5420": "Lewisham",
    "5510": "Merton",
    "5210": "Croydon",
    "5110": "City of London",
    "5990": "Westminster",
}

# TfL manages red routes (TLRN) passing through our boroughs.
# Works on these roads won't match by SWA code — they need geo-filtering.
TFL_SWA_CODE = "0999"


class Settings(BaseSettings):
    # Borough configuration
    target_boroughs: list[str] = [
        "Lambeth", "Southwark", "Wandsworth", "Lewisham",
        "Merton", "Croydon", "City of London", "Westminster",
    ]

    # Notion
    notion_api_key: str = ""
    notion_roadworks_db_id: str = ""

    # Anthropic (optional)
    anthropic_api_key: str = ""

    # App
    webhook_path: str = "/webhook/street-manager"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
