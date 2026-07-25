from __future__ import annotations

import asyncio
from typing import Any

from app.assessment import (
    build_impact_checklist,
    build_impact_suggestions,
    build_prediction_items,
)
from app.providers.partly import PartlyProvider
from app.services.vehicle_service import VehicleService


class AssessmentService:
    def __init__(self, vehicle_service: VehicleService) -> None:
        self.vehicle_service = vehicle_service

    async def build(self, vehicle_id: str) -> dict[str, Any] | None:
        vehicle = await self.vehicle_service.get_vehicle(vehicle_id)
        if vehicle is None:
            return None
        source, provider_key = self.vehicle_service.split_vehicle_id(vehicle_id)

        if source == "partly":
            provider = self.vehicle_service.get_provider(source)
            if not isinstance(provider, PartlyProvider):
                raise RuntimeError("Partly provider is misconfigured")
            prediction_payload, assemblies_payload = await asyncio.gather(
                provider.prediction(provider_key),
                provider.assemblies(provider_key),
            )
            prediction_items = build_prediction_items(
                prediction_payload,
                assemblies_payload,
            )
            impact_items = build_impact_suggestions(
                prediction_items,
                assemblies_payload,
            )
            raw_names = [
                str(item["raw_part_name"])
                for item in prediction_items
            ]
            return {
                "vehicle": vehicle,
                "workflow_mode": "ai_assisted",
                "items": prediction_items + impact_items,
                "catalogue_parts": [],
                "summary": {
                    "ai_candidate_count": len(prediction_items),
                    "impact_check_count": len(impact_items),
                    "catalogue_matches": sum(
                        1
                        for item in prediction_items
                        if item.get("oem_number")
                    ),
                },
                "impact_checklist": build_impact_checklist(raw_names),
                "disclaimer": (
                    "AI and impact-path results are candidates only. "
                    "A qualified technician must confirm the damage, repair "
                    "method, OEM part, and exact vehicle variant."
                ),
            }

        catalogue_parts = await self.vehicle_service.get_parts(vehicle_id)
        return {
            "vehicle": vehicle,
            "workflow_mode": "manual_catalogue",
            "items": [],
            "catalogue_parts": catalogue_parts,
            "summary": {
                "ai_candidate_count": 0,
                "impact_check_count": 0,
                "catalogue_matches": len(catalogue_parts),
            },
            "impact_checklist": [],
            "disclaimer": (
                "This local vehicle has no linked AI prediction. Select damaged "
                "parts from the imported catalogue and have a qualified "
                "technician verify the OEM number and exact vehicle variant."
            ),
        }
