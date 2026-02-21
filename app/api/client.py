"""Async httpx wrapper with auth and credit header parsing."""

from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://api.the-odds-api.com/v4"


class CreditInfo:
    """Parsed credit info from response headers."""

    def __init__(self, remaining: int | None = None, used: int | None = None):
        self.remaining = remaining
        self.used = used


class OddsAPIClient:
    """Async HTTP client for the Odds API."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        kwargs: dict[str, Any] = {"base_url": BASE_URL, "timeout": 15.0}
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**kwargs)
        self.last_credit_info = CreditInfo()

    async def close(self) -> None:
        await self._client.aclose()

    def _parse_credits(self, response: httpx.Response) -> CreditInfo:
        remaining = response.headers.get("x-requests-remaining")
        used = response.headers.get("x-requests-used")
        info = CreditInfo(
            remaining=int(remaining) if remaining else None,
            used=int(used) if used else None,
        )
        self.last_credit_info = info
        return info

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make an authenticated GET request and return JSON."""
        params = params or {}
        params["apiKey"] = self._api_key
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        self._parse_credits(response)
        return response.json()

    async def get_free(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET request for free endpoints (still needs API key)."""
        return await self.get(path, params)
