from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)


class VisibleDamageDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_index: int = Field(ge=0)
    part_name: str
    damage_type: str
    confidence: float = Field(ge=0, le=1)
    severity: float = Field(ge=0, le=1)
    bounding_box: BoundingBox
    visual_evidence: str


class VisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    photos_are_usable: bool
    quality_warnings: list[str]
    impact_zone: str
    impact_direction: str
    impact_severity: float = Field(ge=0, le=1)
    detections: list[VisibleDamageDetection]


class VisionAnalysisError(RuntimeError):
    pass


@dataclass(frozen=True)
class PhotoInput:
    image_id: str
    content_type: str
    body: bytes


class VisionProvider(Protocol):
    name: str
    model: str

    @property
    def configured(self) -> bool:
        ...

    async def analyse(
        self,
        *,
        images: list[PhotoInput],
        vehicle: dict[str, Any],
        impact_hint: str,
    ) -> VisionResult:
        ...


VISION_PROMPT = """
You are a conservative vehicle-collision photo triage system.

Analyse only damage that is directly visible in the supplied photos. Do not
infer hidden damage, do not invent an OEM number, and do not claim that a part
needs replacement. A separate graph and a qualified technician handle those
steps.

Return:
- whether the photos are usable and any quality warnings;
- the most likely impact zone and direction, using "unknown" when uncertain;
- an overall visual impact severity from 0 to 1;
- visible detections with a generic automotive part name, damage type,
  calibrated confidence, severity, concise visual evidence, and a normalised
  bounding box (x1, y1, x2, y2, each from 0 to 1);
- image_index is zero-based in the same order as the supplied images.

Only report a detection when a human can point to corresponding visual
evidence. Reflections, dirt, shadows, panel gaps, and image compression may
look like damage, so lower confidence or omit them. If the input is unrelated
or too unclear, return an empty detections list. Multiple photos may show the
same damaged part; return the clearest observation rather than duplicates.
""".strip()


class OpenAIVisionProvider:
    """Image-reasoning provider using the Responses API.

    This returns conservative boxes, not pixel-perfect segmentation masks.
    A specialised segmentation service can be selected with WebhookVisionProvider.
    """

    name = "openai_vision"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        for item in payload.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    return content["text"]
        raise VisionAnalysisError("The vision model returned no structured text")

    async def analyse(
        self,
        *,
        images: list[PhotoInput],
        vehicle: dict[str, Any],
        impact_hint: str,
    ) -> VisionResult:
        if not self.configured:
            raise VisionAnalysisError(
                "Photo inference is not configured. Set OPENAI_API_KEY or use "
                "the clearly labelled guided-demo mode."
            )

        vehicle_context = " ".join(
            str(vehicle.get(key) or "").strip()
            for key in ("year", "make", "model", "trim")
        ).strip()
        hint = impact_hint.strip() or "unknown"
        input_content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    f"{VISION_PROMPT}\n\nVehicle context: "
                    f"{vehicle_context or 'not supplied'}\n"
                    f"Technician impact-zone hint: {hint}"
                ),
            }
        ]
        for image in images:
            encoded = base64.b64encode(image.body).decode("ascii")
            input_content.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{image.content_type};base64,{encoded}"
                    ),
                    "detail": "high",
                }
            )

        schema = VisionResult.model_json_schema()
        payload = {
            "model": self.model,
            "store": False,
            "input": [{"role": "user", "content": input_content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "vehicle_visible_damage",
                    "strict": True,
                    "schema": schema,
                }
            },
            "max_output_tokens": 4000,
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise VisionAnalysisError(
                f"Could not reach the configured vision API: {exc}"
            ) from exc

        if response.is_error:
            try:
                detail = response.json().get("error", {}).get("message")
            except (ValueError, AttributeError):
                detail = response.text[:300]
            raise VisionAnalysisError(
                f"Vision API returned {response.status_code}: "
                f"{detail or 'unknown error'}"
            )
        try:
            response_payload = response.json()
            result = VisionResult.model_validate_json(
                self._output_text(response_payload)
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise VisionAnalysisError(
                "The vision response did not match the required schema"
            ) from exc

        result.detections = [
            detection
            for detection in result.detections
            if detection.image_index < len(images)
            and detection.bounding_box.x2 > detection.bounding_box.x1
            and detection.bounding_box.y2 > detection.bounding_box.y1
        ]
        return result


class WebhookVisionProvider:
    """Adapter for a specialised part/damage segmentation endpoint.

    The endpoint receives JSON with base64 images and must return VisionResult.
    It can internally run YOLO, Mask R-CNN, SAM, or another segmentation stack.
    """

    name = "segmentation_webhook"

    def __init__(
        self,
        *,
        url: str,
        token: str,
        model: str = "external-segmentation-model",
    ) -> None:
        self.url = url.strip()
        self.token = token.strip()
        self.model = model

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def analyse(
        self,
        *,
        images: list[PhotoInput],
        vehicle: dict[str, Any],
        impact_hint: str,
    ) -> VisionResult:
        if not self.configured:
            raise VisionAnalysisError("VISION_WEBHOOK_URL is not configured")
        body = {
            "vehicle": vehicle,
            "impact_hint": impact_hint,
            "images": [
                {
                    "image_id": image.image_id,
                    "content_type": image.content_type,
                    "base64": base64.b64encode(image.body).decode("ascii"),
                }
                for image in images
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(self.url, headers=headers, json=body)
                response.raise_for_status()
                result = VisionResult.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise VisionAnalysisError(
                f"Segmentation webhook failed: {exc}"
            ) from exc
        return result


def guided_result(
    *,
    visible_part: str,
    damage_type: str,
    severity: float,
    impact_zone: str,
) -> VisionResult:
    """Create an explicit technician seed when no image model is configured."""
    if not visible_part.strip():
        raise VisionAnalysisError(
            "Guided-demo mode requires a technician-entered visible part"
        )
    return VisionResult(
        photos_are_usable=True,
        quality_warnings=[
            "Guided demo, not image inference: the visible part was entered "
            "by the technician and the photo was not interpreted by an AI model."
        ],
        impact_zone=impact_zone or "unknown",
        impact_direction="unknown",
        impact_severity=severity,
        detections=[
            VisibleDamageDetection(
                image_index=0,
                part_name=visible_part.strip(),
                damage_type=damage_type.strip() or "visible damage",
                confidence=1.0,
                severity=severity,
                bounding_box=BoundingBox(x1=0.18, y1=0.35, x2=0.82, y2=0.88),
                visual_evidence=(
                    "Technician-entered seed for workflow demonstration; "
                    "bounding box is illustrative."
                ),
            )
        ],
    )
