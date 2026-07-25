from __future__ import annotations

from typing import Any

from app.assessment import get_assemblies
from app.partly_client import PartlyClient


class PartlyProvider:
    """Translate the hackathon Partly API into Team J's unified format."""

    source = "partly"

    def __init__(self, client: PartlyClient) -> None:
        self.client = client

    @staticmethod
    def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
        provider_key = str(raw.get("slug") or "")
        display_name = str(
            raw.get("display_name")
            or " ".join(
                str(raw.get(field) or "").strip()
                for field in ("year", "make", "model")
            ).strip()
            or provider_key
        )
        part_count = int(raw.get("part_count") or 0)
        diagram_count = int(raw.get("diagram_count") or 0)
        return {
            "id": f"partly:{provider_key}",
            "provider_key": provider_key,
            "slug": f"partly:{provider_key}",
            "display_name": display_name,
            "make": str(raw.get("make") or ""),
            "model": str(raw.get("model") or ""),
            "year": raw.get("year") or "",
            "trim": str(raw.get("trim") or ""),
            "vin": "",
            "source": "partly",
            "capabilities": {
                # Photo analysis is a case-level service, never a property of
                # the selected vehicle.
                "damage_prediction": False,
                "oem_parts": True,
                "diagram": raw.get("diagram_count") != 0,
            },
            "has_prediction": False,
            "part_count": part_count,
            "diagram_count": diagram_count,
        }

    async def list_vehicles(self) -> list[dict[str, Any]]:
        return [
            self._normalise(raw)
            for raw in await self.client.vehicles()
            if raw.get("slug")
        ]

    async def get_vehicle(self, provider_key: str) -> dict[str, Any] | None:
        for raw in await self.client.vehicles():
            if str(raw.get("slug")) == provider_key:
                return self._normalise(raw)
        return None

    async def get_parts(self, provider_key: str) -> list[dict[str, Any]]:
        payload = await self.client.assemblies(provider_key)
        rows: list[dict[str, Any]] = []
        for part_id, part in get_assemblies(payload).items():
            hotspot = part.get("hotspot")
            diagram_id = (
                hotspot.get("diagram_id")
                if isinstance(hotspot, dict)
                else None
            )
            rows.append(
                {
                    "part_id": part_id,
                    "vehicle_id": f"partly:{provider_key}",
                    "part_name": str(part.get("display_name") or part_id),
                    "oem_number": str(
                        part.get("manufacturer_part_number") or ""
                    ),
                    "category": "",
                    "diagram_id": str(diagram_id) if diagram_id else None,
                    "diagram_url": None,
                    "is_orderable": part.get("is_orderable"),
                }
            )
        return rows

    async def prediction(self, provider_key: str) -> dict[str, Any]:
        return await self.client.prediction(provider_key)

    async def assemblies(self, provider_key: str) -> dict[str, Any]:
        return await self.client.assemblies(provider_key)
