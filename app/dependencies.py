from __future__ import annotations

import os
from pathlib import Path

from app.database import Database
from app.partly_client import PartlyClient
from app.providers.local_catalogue import LocalCatalogueProvider
from app.providers.partly import PartlyProvider
from app.services.assessment_service import AssessmentService
from app.services.photo_assessment_service import PhotoAssessmentService
from app.services.vehicle_service import VehicleService
from app.vision import OpenAIVisionProvider, WebhookVisionProvider


APP_DIR = Path(__file__).resolve().parent
PARTLY_API_URL = os.getenv("PARTLY_API_URL", "http://localhost:8420")
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    str(APP_DIR.parent / "storage" / "inspection.db"),
)
PHOTO_STORAGE_PATH = os.getenv(
    "PHOTO_STORAGE_PATH",
    str(APP_DIR.parent / "storage" / "photo-assessments"),
)
VEHICLE_JSON_PATH = os.getenv(
    "VEHICLE_JSON_PATH",
    str(APP_DIR.parent / "data" / "vehicles.json"),
)
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "openai").strip().casefold()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
VISION_WEBHOOK_URL = os.getenv("VISION_WEBHOOK_URL", "")
VISION_WEBHOOK_TOKEN = os.getenv("VISION_WEBHOOK_TOKEN", "")

database = Database(DATABASE_PATH)
partly_client = PartlyClient(PARTLY_API_URL)
partly_provider = PartlyProvider(partly_client, VEHICLE_JSON_PATH)
local_provider = LocalCatalogueProvider(database)
vehicle_service = VehicleService([partly_provider, local_provider])
assessment_service = AssessmentService(vehicle_service)
if VISION_PROVIDER == "webhook":
    vision_provider = WebhookVisionProvider(
        url=VISION_WEBHOOK_URL,
        token=VISION_WEBHOOK_TOKEN,
    )
else:
    vision_provider = OpenAIVisionProvider(
        api_key=OPENAI_API_KEY,
        model=OPENAI_VISION_MODEL,
        base_url=OPENAI_BASE_URL,
    )
photo_assessment_service = PhotoAssessmentService(
    database=database,
    vehicle_service=vehicle_service,
    vision_provider=vision_provider,
    storage_dir=PHOTO_STORAGE_PATH,
)
