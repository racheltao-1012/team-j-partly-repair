import asyncio

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

