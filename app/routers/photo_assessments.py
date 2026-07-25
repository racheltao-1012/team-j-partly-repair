from __future__ import annotations

import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from app.dependencies import database, photo_assessment_service
from app.services.vehicle_service import UnknownVehicleSource
from app.vision import PhotoInput, VisionAnalysisError


router = APIRouter(
    prefix="/api/v1/photo-assessments",
    tags=["photo assessments"],
)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_IMAGES = 4
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def _sanitise_image(body: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(body)) as opened:
            if opened.format not in ALLOWED_FORMATS:
                raise ValueError("Only JPEG, PNG and WEBP photos are accepted")
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((2400, 2400))
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            else:
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded file is not a readable image") from exc


@router.get("/status")
async def photo_status() -> dict[str, Any]:
    return photo_assessment_service.status()


@router.post("/analyse", status_code=201)
async def analyse_photos(
    vehicle_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    mode: Annotated[str, Form()] = "vision",
    impact_hint: Annotated[str, Form()] = "unknown",
    guided_visible_part: Annotated[str, Form()] = "",
    guided_damage_type: Annotated[str, Form()] = "visible damage",
    guided_severity: Annotated[float, Form()] = 0.5,
) -> dict[str, Any]:
    if mode not in {"vision", "guided"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be 'vision' or 'guided'",
        )
    if not 1 <= len(files) <= MAX_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload between 1 and {MAX_IMAGES} vehicle photos",
        )

    images: list[PhotoInput] = []
    total_bytes = 0
    for upload in files:
        body = await upload.read(MAX_IMAGE_BYTES + 1)
        if len(body) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename or 'Image'} exceeds 10 MB",
            )
        total_bytes += len(body)
        if total_bytes > MAX_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Combined photo size exceeds 25 MB",
            )
        try:
            clean_body, content_type = _sanitise_image(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        images.append(
            PhotoInput(
                image_id=str(uuid.uuid4()),
                content_type=content_type,
                body=clean_body,
            )
        )

    try:
        return await photo_assessment_service.analyse(
            vehicle_id=vehicle_id,
            images=images,
            mode=mode,
            impact_hint=impact_hint,
            guided_visible_part=guided_visible_part,
            guided_damage_type=guided_damage_type,
            guided_severity=max(0.0, min(guided_severity, 1.0)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownVehicleSource as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VisionAnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{run_id}")
async def get_photo_assessment(run_id: str) -> dict[str, Any]:
    result = photo_assessment_service.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Photo assessment not found")
    return result


@router.get("/{run_id}/images/{image_id}", include_in_schema=False)
async def get_photo_image(run_id: str, image_id: str) -> FileResponse:
    row = database.get_photo_image(run_id, image_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(
        str(row["stored_path"]),
        media_type=str(row["content_type"]),
    )
