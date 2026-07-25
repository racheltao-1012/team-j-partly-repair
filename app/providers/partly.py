from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.assessment import get_assemblies
from app.partly_client import PartlyAPIError, PartlyClient


class PartlyProvider:
    """Translate the hackathon Partly API into Team J's unified format."""

    source = "partly"

    def __init__(
        self,
        client: PartlyClient,
        fallback_path: str | Path | None = None,
    ) -> None:
        self.client = client
        self.fallback_path = Path(fallback_path) if fallback_path else None
        self.last_api_error: str | None = None
        self.vehicle_data_source = "partly_api"

    @staticmethod
    def _normalise(
        raw: dict[str, Any],
        *,
        data_source: str = "partly_api",
    ) -> dict[str, Any]:
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
            "data_source": data_source,
            "capabilities": {
                # Photo analysis is a case-level service, never a property of
                # the selected vehicle.
                "damage_prediction": False,
                "oem_parts": data_source == "partly_api",
                "diagram": (
                    data_source == "partly_api"
                    and raw.get("diagram_count") != 0
                ),
            },
            "has_prediction": False,
            "part_count": part_count,
            "diagram_count": diagram_count,
        }

    def _fallback_vehicles(self) -> list[dict[str, Any]]:
        if self.fallback_path is None or not self.fallback_path.is_file():
            return []
        try:
            payload = json.loads(self.fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PartlyAPIError(
                f"Could not read vehicle JSON fallback at {self.fallback_path}: {exc}"
            ) from exc
        if not isinstance(payload, list):
            raise PartlyAPIError("Vehicle JSON fallback must contain a list")
        return [
            item
            for item in payload
            if isinstance(item, dict) and item.get("slug")
        ]

    async def _vehicle_rows(self) -> list[dict[str, Any]]:
        try:
            rows = await self.client.vehicles()
        except PartlyAPIError as exc:
            self.last_api_error = str(exc)
            rows = self._fallback_vehicles()
            if not rows:
                raise
            self.vehicle_data_source = "json_fallback"
            return rows
        self.last_api_error = None
        self.vehicle_data_source = "partly_api"
        return rows

    async def list_vehicles(self) -> list[dict[str, Any]]:
        return [
            self._normalise(raw, data_source=self.vehicle_data_source)
            for raw in await self._vehicle_rows()
            if raw.get("slug")
        ]

    async def get_vehicle(self, provider_key: str) -> dict[str, Any] | None:
        rows = await self._vehicle_rows()
        for raw in rows:
            if str(raw.get("slug")) == provider_key:
                return self._normalise(
                    raw,
                    data_source=self.vehicle_data_source,
                )
        return None

    async def get_parts(self, provider_key: str) -> list[dict[str, Any]]:
        try:
            payload = await self.client.assemblies(provider_key)
        except PartlyAPIError:
            if self._fallback_vehicles():
                return []
            raise
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
