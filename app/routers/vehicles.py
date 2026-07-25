from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.dependencies import database, local_provider
from app.dependencies import vehicle_service
from app.partly_client import PartlyAPIError
from app.schemas import PartCreate, VehicleCreate
from app.services.vehicle_service import UnknownVehicleSource


router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


@router.get("")
async def list_vehicles() -> list[dict[str, Any]]:
    return await vehicle_service.list_vehicles()


@router.post("", status_code=201)
async def create_vehicle(payload: VehicleCreate) -> dict[str, Any]:
    row = database.create_vehicle(payload.model_dump())
    return local_provider._normalise(row)


@router.get("/{vehicle_id}/parts")
async def get_vehicle_parts(vehicle_id: str) -> list[dict[str, Any]]:
    try:
        vehicle = await vehicle_service.get_vehicle(vehicle_id)
        if vehicle is None:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        return await vehicle_service.get_parts(vehicle_id)
    except UnknownVehicleSource as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PartlyAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{vehicle_id}/parts", status_code=201)
async def create_vehicle_part(
    vehicle_id: str,
    payload: PartCreate,
) -> dict[str, Any]:
    try:
        source, provider_key = vehicle_service.split_vehicle_id(vehicle_id)
    except UnknownVehicleSource as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if source != "local":
        raise HTTPException(
            status_code=400,
            detail="Parts can only be added to local vehicles",
        )
    try:
        row = database.create_part(
            provider_key,
            payload.model_dump(mode="json"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return local_provider._normalise_part(row)


@router.get("/{vehicle_id}/assessment")
async def get_vehicle_assessment(vehicle_id: str) -> dict[str, Any]:
    raise HTTPException(
        status_code=409,
        detail=(
            "Vehicle-only damage assessment is disabled. Upload current-case "
            "photos to /api/v1/photo-assessments/analyse."
        ),
    )
