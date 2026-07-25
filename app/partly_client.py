from __future__ import annotations

from typing import Any

import httpx


class PartlyAPIError(RuntimeError):
    pass


class PartlyClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _request(self, path: str) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(20.0),
            ) as client:
                response = await client.get(path)
                response.raise_for_status()
                return response
        except httpx.HTTPError as exc:
            raise PartlyAPIError(
                f"Could not read Partly API at {self.base_url}{path}: {exc}"
            ) from exc

    async def get_json(self, path: str) -> Any:
        response = await self._request(path)
        try:
            return response.json()
        except ValueError as exc:
            raise PartlyAPIError(f"Partly API returned invalid JSON for {path}") from exc

    async def get_bytes(self, path: str) -> tuple[bytes, str]:
        response = await self._request(path)
        return response.content, response.headers.get(
            "content-type",
            "application/octet-stream",
        )

    async def vehicles(self) -> list[dict[str, Any]]:
        payload = await self.get_json("/vehicles")
        if not isinstance(payload, list):
            raise PartlyAPIError("Partly /vehicles response is not a list")
        return [item for item in payload if isinstance(item, dict)]

    async def prediction(self, slug: str) -> dict[str, Any]:
        payload = await self.get_json(f"/vehicles/{slug}/predictions")
        if not isinstance(payload, dict):
            raise PartlyAPIError("Prediction response is not an object")
        return payload

    async def assemblies(self, slug: str) -> dict[str, Any]:
        payload = await self.get_json(f"/vehicles/{slug}/assemblies")
        if not isinstance(payload, dict):
            raise PartlyAPIError("Assemblies response is not an object")
        return payload

