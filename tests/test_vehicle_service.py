import asyncio
import json

from app.partly_client import PartlyAPIError
from app.providers.partly import PartlyProvider
from app.services.vehicle_service import VehicleService


class WorkingProvider:
    source = "local"

    async def list_vehicles(self):
        return [{"id": "local:1", "source": "local_catalogue"}]

    async def get_vehicle(self, provider_key):
        return {"id": f"local:{provider_key}"}

    async def get_parts(self, provider_key):
        return [{"part_id": "part-1", "vehicle_id": f"local:{provider_key}"}]


class FailingProvider:
    source = "partly"

    async def list_vehicles(self):
        raise RuntimeError("offline")

    async def get_vehicle(self, provider_key):
        raise RuntimeError("offline")

    async def get_parts(self, provider_key):
        raise RuntimeError("offline")


def test_provider_failure_does_not_hide_local_vehicles():
    service = VehicleService([FailingProvider(), WorkingProvider()])
    vehicles = asyncio.run(service.list_vehicles())

    assert vehicles == [{"id": "local:1", "source": "local_catalogue"}]
    assert "partly" in service.last_errors
    assert asyncio.run(service.get_parts("local:1"))[0]["part_id"] == "part-1"


class OfflinePartlyClient:
    async def vehicles(self):
        raise PartlyAPIError("offline")

    async def assemblies(self, _provider_key):
        raise PartlyAPIError("offline")


def test_partly_provider_uses_json_vehicle_fallback(tmp_path):
    fallback_path = tmp_path / "vehicles.json"
    fallback_path.write_text(
        json.dumps(
            [
                {
                    "slug": "toyota-yaris-qmn16",
                    "make": "toyota",
                    "model": "YARIS",
                    "year": 2023,
                    "diagram_count": 187,
                    "part_count": 7009,
                }
            ]
        ),
        encoding="utf-8",
    )
    provider = PartlyProvider(OfflinePartlyClient(), fallback_path)

    vehicles = asyncio.run(provider.list_vehicles())

    assert len(vehicles) == 1
    assert vehicles[0]["id"] == "partly:toyota-yaris-qmn16"
    assert vehicles[0]["data_source"] == "json_fallback"
    assert vehicles[0]["capabilities"]["oem_parts"] is False
    assert provider.vehicle_data_source == "json_fallback"
    assert provider.last_api_error == "offline"
    assert asyncio.run(provider.get_parts("toyota-yaris-qmn16")) == []
