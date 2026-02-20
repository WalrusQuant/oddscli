"""Typed fetch functions for the Odds API."""

from __future__ import annotations

from app.api.client import OddsAPIClient
from app.api.models import Event, Score, Sport


async def get_sports(client: OddsAPIClient) -> list[Sport]:
    """Fetch all available sports (free endpoint)."""
    data = await client.get_free("/sports")
    return [Sport(**s) for s in data]


async def get_odds(
    client: OddsAPIClient,
    sport: str,
    *,
    regions: str = "us",
    markets: str = "h2h,spreads,totals",
    odds_format: str = "american",
    bookmakers: list[str] | None = None,
) -> list[Event]:
    """Fetch odds for a sport. Costs credits."""
    params: dict = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
    }
    if bookmakers:
        params["bookmakers"] = ",".join(bookmakers)
    data = await client.get(f"/sports/{sport}/odds", params=params)
    return [Event(**e) for e in data]


async def get_scores(
    client: OddsAPIClient,
    sport: str,
    *,
    days_from: int = 1,
) -> list[Score]:
    """Fetch live & recent scores. Costs 1 credit per request."""
    params = {"daysFrom": days_from}
    data = await client.get(f"/sports/{sport}/scores", params=params)
    return [Score(**s) for s in data]


async def get_events(client: OddsAPIClient, sport: str) -> list[dict]:
    """Fetch events for a sport (free endpoint)."""
    data = await client.get_free(f"/sports/{sport}/events")
    return data
