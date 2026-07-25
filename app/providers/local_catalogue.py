from __future__ import annotations

from typing import Any

from app.database import Database


class LocalCatalogueProvider:
    """Expose technician-created vehicles and imported OEM catalogues."""

    source = "local"

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
        provider_key = str(raw["vehicle_id"])
        part_count = int(raw.get("part_count") or 0)
        diagram_count = int(raw.get("diagram_count") or 0)
        display_name = " ".join(
            str(raw.get(field) or "").strip()
            for field in ("year", "make", "model", "trim")
        ).strip()
        return {
            "id": f"local:{provider_key}",
            "provider_key": provider_key,
            "slug": f"local:{provider_key}",
            "display_name": display_name,
            "make": str(raw.get("make") or ""),
            "model": str(raw.get("model") or ""),
            "year": raw.get("year") or "",
            "trim": str(raw.get("trim") or ""),
            "vin": str(raw.get("vin") or ""),
            "source": "local_catalogue",
            "capabilities": {
                "damage_prediction": False,
                "oem_parts": part_count > 0,
                "diagram": diagram_count > 0,
            },
            "has_prediction": False,
            "part_count": part_count,
            "diagram_count": diagram_count,
        }

    @staticmethod
    def _normalise_part(raw: dict[str, Any]) -> dict[str, Any]:
        diagram_url = str(raw.get("diagram_url") or "")
        return {
            "part_id": str(raw["part_id"]),
            "vehicle_id": f"local:{raw['vehicle_id']}",
            "part_name": str(raw.get("part_name") or ""),
            "oem_number": str(raw.get("oem_number") or ""),
            "category": str(raw.get("category") or ""),
            "diagram_id": str(raw["part_id"]) if diagram_url else None,
            "diagram_url": diagram_url or None,
            "is_orderable": None,
        }

    async def list_vehicles(self) -> list[dict[str, Any]]:
        return [
            self._normalise(row)
            for row in self.database.list_local_vehicles()
        ]

    async def get_vehicle(self, provider_key: str) -> dict[str, Any] | None:
        row = self.database.get_local_vehicle(provider_key)
        return self._normalise(row) if row else None

    async def get_parts(self, provider_key: str) -> list[dict[str, Any]]:
        return [
            self._normalise_part(row)
            for row in self.database.get_parts(provider_key)
        ]

