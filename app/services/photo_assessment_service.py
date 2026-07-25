from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.case_similarity import text_similarity
from app.impact_graph import ImpactPropagationService
from app.part_matching import catalogue_match
from app.services.vehicle_service import VehicleService
from app.vision import (
    PhotoInput,
    VisionAnalysisError,
    VisionProvider,
    guided_result,
)


class PhotoAssessmentService:
    def __init__(
        self,
        *,
        database: Any,
        vehicle_service: VehicleService,
        vision_provider: VisionProvider,
        storage_dir: str | Path,
    ) -> None:
        self.database = database
        self.vehicle_service = vehicle_service
        self.vision_provider = vision_provider
        self.storage_dir = Path(storage_dir)
        self.impact_service = ImpactPropagationService(database)

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.vision_provider.configured,
            "provider": self.vision_provider.name,
            "model": self.vision_provider.model,
            "guided_demo_available": True,
            "default_mode": (
                "vision" if self.vision_provider.configured else "guided"
            ),
            "segmentation_note": (
                "The OpenAI provider returns conservative visible-damage boxes. "
                "Set VISION_PROVIDER=webhook for a specialised mask/segmentation "
                "model."
            ),
        }

    async def analyse(
        self,
        *,
        vehicle_id: str,
        images: list[PhotoInput],
        mode: str,
        impact_hint: str,
        guided_visible_part: str,
        guided_damage_type: str,
        guided_severity: float,
    ) -> dict[str, Any]:
        vehicle = await self.vehicle_service.get_vehicle(vehicle_id)
        if vehicle is None:
            raise KeyError("Vehicle not found")
        catalogue_parts = await self.vehicle_service.get_parts(vehicle_id)

        if mode == "guided":
            result = guided_result(
                visible_part=guided_visible_part,
                damage_type=guided_damage_type,
                severity=guided_severity,
                impact_zone=impact_hint,
            )
            provider_name = "technician_guided_demo"
            model_name = "none"
        else:
            if not self.vision_provider.configured:
                raise VisionAnalysisError(
                    "A real photo model is not configured. Choose guided-demo "
                    "mode or configure the vision provider."
                )
            result = await self.vision_provider.analyse(
                images=images,
                vehicle=vehicle,
                impact_hint=impact_hint,
            )
            provider_name = self.vision_provider.name
            model_name = self.vision_provider.model

        run_id = str(uuid.uuid4())
        run_dir = self.storage_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        image_rows: list[dict[str, Any]] = []
        for order, image in enumerate(images):
            suffix = ".png" if image.content_type == "image/png" else ".jpg"
            stored_name = f"{image.image_id}{suffix}"
            path = run_dir / stored_name
            path.write_bytes(image.body)
            image_rows.append(
                {
                    "image_id": image.image_id,
                    "stored_path": str(path),
                    "content_type": image.content_type,
                    "sort_order": order,
                    "size_bytes": len(image.body),
                    "url": (
                        f"/api/v1/photo-assessments/{run_id}/images/"
                        f"{image.image_id}"
                    ),
                }
            )

        visible_items: list[dict[str, Any]] = []
        raw_detections: list[dict[str, Any]] = []
        for detection in result.detections:
            detection_dict = detection.model_dump()
            raw_detections.append(detection_dict)
            image = image_rows[detection.image_index]
            matched_part, match_score = catalogue_match(
                detection.part_name,
                catalogue_parts,
            )
            guided = provider_name == "technician_guided_demo"
            visible_items.append(
                {
                    "source": "manual" if guided else "visible_damage",
                    "raw_part_name": detection.part_name,
                    "predicted_part_id": (
                        matched_part.get("part_id") if matched_part else None
                    ),
                    "predicted_part_name": (
                        matched_part.get("part_name")
                        if matched_part
                        else detection.part_name
                    ),
                    "oem_number": (
                        matched_part.get("oem_number") if matched_part else None
                    ),
                    "diagram_id": (
                        matched_part.get("diagram_id") if matched_part else None
                    ),
                    "diagram_url": (
                        matched_part.get("diagram_url") if matched_part else None
                    ),
                    "ai_confidence": (
                        None if guided else detection.confidence
                    ),
                    "ai_action": (
                        "Technician-entered visible damage seed"
                        if guided
                        else "Visible damage candidate from uploaded photo"
                    ),
                    "technician_decision": "Pending" if not guided else "Confirm",
                    "rejection_reason": "",
                    "corrected_part_id": "",
                    "corrected_part_name": "",
                    "technician_note": "",
                    "hotspot": None,
                    "damage_type": detection.damage_type,
                    "severity": detection.severity,
                    "evidence_image_id": image["image_id"],
                    "evidence_image_url": image["url"],
                    "evidence_box": (
                        None if guided else detection.bounding_box.model_dump()
                    ),
                    "reason": detection.visual_evidence,
                    "propagation_path": [],
                    "probability_band": "",
                    "catalogue_match_score": round(match_score, 4),
                }
            )

        hidden = self.impact_service.propagate(
            detections=raw_detections,
            impact_zone=result.impact_zone,
            impact_severity=result.impact_severity,
            catalogue_parts=catalogue_parts,
        )
        hidden_items: list[dict[str, Any]] = []
        for suggestion in hidden:
            matched_part = suggestion["catalogue_part"]
            hidden_items.append(
                {
                    "source": "impact_path",
                    "raw_part_name": (
                        f"From {suggestion['source_visible_part']}"
                    ),
                    "predicted_part_id": (
                        matched_part.get("part_id") if matched_part else None
                    ),
                    "predicted_part_name": suggestion["display_name"],
                    "oem_number": (
                        matched_part.get("oem_number") if matched_part else None
                    ),
                    "diagram_id": (
                        matched_part.get("diagram_id") if matched_part else None
                    ),
                    "diagram_url": (
                        matched_part.get("diagram_url") if matched_part else None
                    ),
                    "ai_confidence": suggestion["probability"],
                    "ai_action": (
                        "Recommended for inspection; not confirmed damage"
                    ),
                    "technician_decision": "Needs inspection",
                    "rejection_reason": "",
                    "corrected_part_id": "",
                    "corrected_part_name": "",
                    "technician_note": "",
                    "hotspot": None,
                    "damage_type": "suspected hidden impact",
                    "severity": None,
                    "evidence_image_id": None,
                    "evidence_image_url": None,
                    "evidence_box": None,
                    "reason": (
                        "Load-path probability based on the visible impact "
                        "seed and part relationship graph"
                    ),
                    "propagation_path": suggestion["path"],
                    "probability_band": suggestion["probability_band"],
                    "catalogue_match_score": suggestion[
                        "catalogue_match_score"
                    ],
                }
            )

        similar_cases = self.database.find_similar_cases(
            vehicle_slug=vehicle_id,
            impact_zone=result.impact_zone,
            impact_severity=result.impact_severity,
            visible_items=visible_items,
        )
        existing_names = [
            str(item.get("predicted_part_name") or item.get("raw_part_name") or "")
            for item in visible_items + hidden_items
        ]
        historical_items: list[dict[str, Any]] = []
        for recommendation in similar_cases["recommendations"]:
            part_name = str(recommendation["part_name"])
            if max(
                (
                    text_similarity(part_name, existing_name)
                    for existing_name in existing_names
                ),
                default=0.0,
            ) >= 0.65:
                continue
            matched_part, match_score = catalogue_match(
                part_name,
                catalogue_parts,
            )
            # Historical suggestions use a stricter catalogue threshold than
            # direct visible detections so a fuzzy past-case name never
            # inherits an unrelated OEM number.
            if match_score < 0.65:
                matched_part = None
            relevance = float(recommendation["relevance"])
            support_count = int(recommendation["support_count"])
            historical_items.append(
                {
                    "source": "historical_case",
                    "raw_part_name": "Similar technician-confirmed cases",
                    "predicted_part_id": (
                        matched_part.get("part_id") if matched_part else None
                    ),
                    "predicted_part_name": (
                        matched_part.get("part_name")
                        if matched_part
                        else part_name
                    ),
                    "oem_number": (
                        matched_part.get("oem_number")
                        if matched_part
                        else recommendation.get("oem_number")
                    ),
                    "diagram_id": (
                        matched_part.get("diagram_id") if matched_part else None
                    ),
                    "diagram_url": (
                        matched_part.get("diagram_url") if matched_part else None
                    ),
                    "ai_confidence": relevance,
                    "ai_action": (
                        "Recommended for inspection from similar saved cases; "
                        "not photo-confirmed damage"
                    ),
                    "technician_decision": "Needs inspection",
                    "rejection_reason": "",
                    "corrected_part_id": "",
                    "corrected_part_name": "",
                    "technician_note": "",
                    "hotspot": None,
                    "damage_type": "historical inspection suggestion",
                    "severity": None,
                    "evidence_image_id": None,
                    "evidence_image_url": None,
                    "evidence_box": None,
                    "reason": recommendation["reason"],
                    "propagation_path": [],
                    "probability_band": "case relevance",
                    "catalogue_match_score": round(match_score, 4),
                    "historical_support_count": support_count,
                    "similar_case_ids": recommendation["case_ids"],
                }
            )
            existing_names.append(part_name)

        impact_checklist = [
            {
                "damage_area": item["source_visible_part"],
                "inspect": [item["display_name"]],
                "probability": item["probability"],
                "probability_band": item["probability_band"],
                "path": item["path"],
                "disclaimer": (
                    "Inspection suggestion only; technician confirmation required."
                ),
            }
            for item in hidden
        ]
        response = {
            "vehicle": vehicle,
            "workflow_mode": (
                "guided_photo_workflow"
                if provider_name == "technician_guided_demo"
                else "photo_vision"
            ),
            "items": visible_items + hidden_items + historical_items,
            "catalogue_parts": catalogue_parts,
            "summary": {
                "ai_candidate_count": len(visible_items),
                "visible_damage_count": len(visible_items),
                "impact_check_count": len(hidden_items),
                "historical_check_count": len(historical_items),
                "similar_case_count": similar_cases["match_count"],
                "catalogue_matches": sum(
                    1
                    for item in visible_items + hidden_items + historical_items
                    if item.get("oem_number")
                ),
            },
            "impact_checklist": impact_checklist,
            "similar_cases": similar_cases,
            "photo_assessment": {
                "run_id": run_id,
                "provider": provider_name,
                "model": model_name,
                "images": image_rows,
                "photos_are_usable": result.photos_are_usable,
                "quality_warnings": result.quality_warnings,
                "impact_zone": result.impact_zone,
                "impact_direction": result.impact_direction,
                "impact_severity": result.impact_severity,
            },
            "disclaimer": (
                "Visible results come from this photo run only. Impact-path and "
                "similar-case suggestions are inspection prompts, not diagnoses "
                "or photo-confirmed damage. A qualified technician must inspect "
                "the vehicle and confirm damage, repair method, exact variant, "
                "and OEM number."
            ),
        }
        self.database.create_photo_assessment(
            run_id=run_id,
            vehicle_id=vehicle_id,
            provider=provider_name,
            model=model_name,
            impact_zone=result.impact_zone,
            impact_direction=result.impact_direction,
            impact_severity=result.impact_severity,
            images=image_rows,
            result=response,
        )
        return response

    def get(self, run_id: str) -> dict[str, Any] | None:
        row = self.database.get_photo_assessment(run_id)
        if row is None:
            return None
        return json.loads(str(row["result_json"]))
