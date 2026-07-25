from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.dependencies import (
    PARTLY_API_URL,
    database,
    photo_assessment_service,
    partly_client,
    vehicle_service,
)
from app.partly_client import PartlyAPIError
from app.routers.catalogues import router as catalogues_router
from app.routers.photo_assessments import router as photo_assessments_router
from app.routers.vehicles import router as vehicles_router
from app.schemas import CaseCreate


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.initialise()
    yield


app = FastAPI(
    title="Team J Inspection Companion",
    description=(
        "Extensible technician verification workflow over Partly and "
        "technician-supplied vehicle catalogues."
    ),
    version="0.4.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(vehicles_router)
app.include_router(catalogues_router)
app.include_router(photo_assessments_router)


def partly_error(exc: PartlyAPIError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail=(
            f"{exc}. Make sure the official Partly API is running on port 8420."
        ),
    )


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    vehicles = await vehicle_service.list_vehicles()
    partly_connected = "partly" not in vehicle_service.last_errors
    source_counts: dict[str, int] = {}
    for vehicle in vehicles:
        source = str(vehicle.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "status": "ok" if partly_connected else "degraded",
        "partly_api_connected": partly_connected,
        "vehicle_count": len(vehicles),
        "source_counts": source_counts,
        "provider_errors": vehicle_service.last_errors,
        "partly_api_url": PARTLY_API_URL,
        "photo_analysis": photo_assessment_service.status(),
    }


@app.get("/api/v1/part-relations", tags=["impact propagation"])
async def part_relations() -> list[dict[str, Any]]:
    """Expose the auditable graph used for hidden-damage inspection ranking."""
    return database.list_part_relations()


@app.get("/api/vehicles")
async def vehicles() -> list[dict[str, Any]]:
    """Backwards-compatible alias; new code should use /api/v1/vehicles."""
    return await vehicle_service.list_vehicles()


@app.get("/api/vehicles/{slug}/assessment")
async def assessment(slug: str) -> dict[str, Any]:
    """Reject the old vehicle-bound prediction path."""
    raise HTTPException(
        status_code=409,
        detail=(
            "Fixed vehicle predictions are disabled. Upload current-case "
            "photos to /api/v1/photo-assessments/analyse."
        ),
    )


@app.get("/api/partly/vehicles/{slug}/diagrams/{diagram_id}/image")
async def diagram_image(slug: str, diagram_id: str) -> Response:
    try:
        body, content_type = await partly_client.get_bytes(
            f"/vehicles/{slug}/diagrams/{diagram_id}/image"
        )
    except PartlyAPIError as exc:
        raise partly_error(exc) from exc
    return Response(content=body, media_type=content_type)


@app.get("/api/partly/vehicles/{slug}/diagrams/{diagram_id}/meta")
async def diagram_meta(slug: str, diagram_id: str) -> Any:
    try:
        return await partly_client.get_json(
            f"/vehicles/{slug}/diagrams/{diagram_id}/meta"
        )
    except PartlyAPIError as exc:
        raise partly_error(exc) from exc


@app.post("/api/cases", status_code=201)
async def create_case(payload: CaseCreate) -> dict[str, str]:
    case_id = database.create_case(payload.model_dump())
    return {
        "case_id": case_id,
        "report_url": f"/api/cases/{case_id}",
        "csv_url": f"/api/cases/{case_id}/export.csv",
    }


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str) -> dict[str, Any]:
    case = database.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/api/cases/{case_id}/export.csv")
async def export_case(case_id: str) -> Response:
    csv_body = database.export_csv(case_id)
    if csv_body is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="damage-assessment-{case_id[:8]}.csv"'
            )
        },
    )


@app.get("/api/history/{vehicle_slug}")
async def vehicle_history(vehicle_slug: str) -> dict[str, Any]:
    return database.history(vehicle_slug)
