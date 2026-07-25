from __future__ import annotations

import asyncio
from typing import Any

from app.providers.base import VehicleProvider


class UnknownVehicleSource(ValueError):
    pass


class VehicleService:
    """Merge providers while keeping provider-specific details isolated."""

    def __init__(self, providers: list[VehicleProvider]) -> None:
        self.providers = {provider.source: provider for provider in providers}
        self.last_errors: dict[str, str] = {}

    @staticmethod
    def split_vehicle_id(vehicle_id: str) -> tuple[str, str]:
        if ":" not in vehicle_id:
            # Backwards compatibility for the first MVP's Partly slugs.
            return "partly", vehicle_id
        source, provider_key = vehicle_id.split(":", 1)
        if not source or not provider_key:
            raise UnknownVehicleSource("Vehicle ID is invalid")
        return source, provider_key

    def get_provider(self, source: str) -> VehicleProvider:
        provider = self.providers.get(source)
        if provider is None:
            raise UnknownVehicleSource(f"Unknown vehicle source: {source}")
        return provider

    async def list_vehicles(self) -> list[dict[str, Any]]:
        provider_items = list(self.providers.items())
        results = await asyncio.gather(
            *(provider.list_vehicles() for _, provider in provider_items),
            return_exceptions=True,
        )
        vehicles: list[dict[str, Any]] = []
        self.last_errors = {}
        for (source, _provider), result in zip(provider_items, results, strict=True):
            if isinstance(result, Exception):
                self.last_errors[source] = str(result)
                continue
            vehicles.extend(result)
        return vehicles

    async def get_vehicle(self, vehicle_id: str) -> dict[str, Any] | None:
        source, provider_key = self.split_vehicle_id(vehicle_id)
        return await self.get_provider(source).get_vehicle(provider_key)

    async def get_parts(self, vehicle_id: str) -> list[dict[str, Any]]:
        source, provider_key = self.split_vehicle_id(vehicle_id)
        return await self.get_provider(source).get_parts(provider_key)

