"""Typed fetch functions for the Odds API."""

from __future__ import annotations

import asyncio
import logging

from app.api.client import OddsAPIClient
from app.api.models import Event, Score, Sport

log = logging.getLogger(__name__)


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


async def get_event_odds(
    client: OddsAPIClient,
    sport: str,
    event_id: str,
    *,
    regions: str = "us",
    markets: str = "player_pass_yds",
    odds_format: str = "american",
    bookmakers: list[str] | None = None,
) -> Event:
    """Fetch odds for a single event. Costs credits."""
    params: dict = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
    }
    if bookmakers:
        params["bookmakers"] = ",".join(bookmakers)
    data = await client.get(
        f"/sports/{sport}/events/{event_id}/odds", params=params
    )
    return Event(**data)


async def get_props_for_events(
    client: OddsAPIClient,
    sport: str,
    event_ids: list[str],
    *,
    regions: str = "us",
    markets: str = "player_points",
    odds_format: str = "american",
    bookmakers: list[str] | None = None,
    max_concurrent: int = 5,
) -> list[Event]:
    """Fetch prop odds for multiple events concurrently.

    Resilient to individual failures — returns only successful results.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _fetch_one(eid: str) -> Event | None:
        async with sem:
            try:
                return await get_event_odds(
                    client,
                    sport,
                    eid,
                    regions=regions,
                    markets=markets,
                    odds_format=odds_format,
                    bookmakers=bookmakers,
                )
            except Exception as exc:
                log.warning("Failed to fetch props for event %s: %s", eid, exc)
                return None

    results = await asyncio.gather(*[_fetch_one(eid) for eid in event_ids])
    return [e for e in results if e is not None]
