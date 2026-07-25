from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.dependencies import database, vehicle_service
from app.schemas import PartCreate
from app.services.vehicle_service import UnknownVehicleSource


router = APIRouter(prefix="/api/v1/catalogues", tags=["catalogues"])

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
REQUIRED_COLUMNS = {"part_name", "oem_number"}


@router.post("/import")
async def import_catalogue(
    vehicle_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        source, provider_key = vehicle_service.split_vehicle_id(vehicle_id)
    except UnknownVehicleSource as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if source != "local":
        raise HTTPException(
            status_code=400,
            detail="CSV catalogues can only be imported for local vehicles",
        )
    if database.get_local_vehicle(provider_key) is None:
        raise HTTPException(status_code=404, detail="Local vehicle not found")

    body = await file.read(MAX_FILE_BYTES + 1)
    if len(body) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="CSV is larger than the 5 MB prototype limit",
        )
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="CSV must use UTF-8 encoding",
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    columns = {
        str(column or "").strip().casefold()
        for column in (reader.fieldnames or [])
    }
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV is missing required columns: "
                + ", ".join(sorted(missing))
            ),
        )

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, raw in enumerate(reader, start=2):
        if line_number > MAX_ROWS + 1:
            raise HTTPException(
                status_code=413,
                detail=f"CSV exceeds the {MAX_ROWS}-row prototype limit",
            )
        canonical = {
            str(key or "").strip().casefold(): value
            for key, value in raw.items()
        }
        if not any(str(value or "").strip() for value in canonical.values()):
            continue
        try:
            part = PartCreate.model_validate(
                {
                    "part_name": canonical.get("part_name", ""),
                    "oem_number": canonical.get("oem_number", ""),
                    "category": canonical.get("category", ""),
                    "diagram_url": canonical.get("diagram_url") or None,
                }
            )
        except ValidationError as exc:
            first = exc.errors()[0].get("msg", "invalid value")
            errors.append(f"line {line_number}: {first}")
            if len(errors) >= 10:
                break
            continue
        rows.append(part.model_dump(mode="json"))

    if errors:
        raise HTTPException(
            status_code=400,
            detail="CSV validation failed: " + "; ".join(errors),
        )
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="CSV contains no valid part rows",
        )

    result = database.import_parts(provider_key, rows)
    return {
        "vehicle_id": vehicle_id,
        "file_name": file.filename,
        **result,
    }

