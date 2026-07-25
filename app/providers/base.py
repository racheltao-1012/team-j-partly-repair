from __future__ import annotations

from typing import Any, Protocol


class VehicleProvider(Protocol):
    """Contract implemented by every vehicle data source."""

    source: str

    async def list_vehicles(self) -> list[dict[str, Any]]:
        ...

    async def get_vehicle(self, provider_key: str) -> dict[str, Any] | None:
        ...

    async def get_parts(self, provider_key: str) -> list[dict[str, Any]]:
        ...

