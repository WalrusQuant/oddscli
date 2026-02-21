"""Orchestrator: merge scores+odds, run EV detection, respect budget."""

from __future__ import annotations

import asyncio
import logging

from app.api.client import OddsAPIClient
from app.api.endpoints import (
    get_event_odds,
    get_events,
    get_odds,
    get_props_for_events,
    get_scores,
    get_sports,
)
from app.api.models import Bookmaker, Event, GameRow, PropRow, Score, Sport
from app.config import Settings
from app.services.budget import BudgetTracker
from app.services.cache import TTLCache
from app.services.ev import ArbBet, EVBet, MiddleBet, find_arb_bets, find_ev_bets, find_middle_bets
from app.services.ev_store import EVStore

log = logging.getLogger(__name__)

ALT_MARKETS = "alternate_spreads,alternate_totals"


class DataService:
    """Orchestrates API fetches, caching, merging, and EV detection."""

    def __init__(
        self,
        settings: Settings,
        client: OddsAPIClient | None = None,
        cache: TTLCache | None = None,
        budget: BudgetTracker | None = None,
        ev_store: EVStore | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or OddsAPIClient(settings.api_key)
        self.cache = cache or TTLCache()
        self.budget = budget or BudgetTracker(
            low_warning=settings.low_credit_warning,
            critical_stop=settings.critical_credit_stop,
        )
        self.ev_store = ev_store or EVStore()
        self._sports_cache: list[Sport] = []

    async def close(self) -> None:
        await self.client.close()
        self.ev_store.close()

    def _sync_budget(self) -> None:
        info = self.client.last_credit_info
        self.budget.update(info.remaining, info.used)

    async def fetch_sports(self) -> list[Sport]:
        """Fetch available sports (free endpoint)."""
        cached = self.cache.get("sports")
        if cached is not None:
            return cached
        try:
            sports = await get_sports(self.client)
            self._sports_cache = sports
            self.cache.set("sports", sports, ttl=3600)
            return sports
        except Exception:
            log.exception("Failed to fetch sports")
            return self._sports_cache

    async def has_events(self, sport: str) -> bool:
        """Check if a sport has any events (free endpoint)."""
        cache_key = f"{sport}:events_check"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            events = await get_events(self.client, sport)
            has = len(events) > 0
            self.cache.set(cache_key, has, ttl=600)
            return has
        except Exception:
            return True

    async def fetch_scores(self, sport: str) -> list[Score]:
        """Fetch live scores (costs 1 credit)."""
        if not self.budget.can_fetch_scores:
            log.warning("Budget critical, skipping scores fetch")
            return self.cache.get(f"{sport}:scores") or []

        cache_key = f"{sport}:scores"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            scores = await get_scores(self.client, sport)
            self._sync_budget()
            self.cache.set(cache_key, scores, ttl=self.settings.scores_refresh_interval)
            return scores
        except Exception:
            log.exception("Failed to fetch scores for %s", sport)
            return []

    async def fetch_odds(self, sport: str) -> list[Event]:
        """Fetch odds using the bulk endpoint (h2h, spreads, totals only).

        Alt lines require per-event calls — use fetch_alt_lines() separately.
        """
        if not self.budget.can_fetch_odds:
            log.warning("Budget low, skipping odds fetch")
            return self.cache.get(f"{sport}:odds") or []

        cache_key = f"{sport}:odds"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            events = await get_odds(
                self.client,
                sport,
                regions=self.settings.regions_str,
                markets="h2h,spreads,totals",
                odds_format=self.settings.odds_format,
                bookmakers=self.settings.bookmakers,
            )
            self._sync_budget()
            self.cache.set(cache_key, events, ttl=self.settings.odds_refresh_interval)
            return events
        except Exception:
            log.exception("Failed to fetch odds for %s", sport)
            return []

    async def fetch_alt_lines(self, sport: str, events: list[Event]) -> list[Event]:
        """Fetch alternate lines per-event and merge into existing events.

        Alt markets (alternate_spreads, alternate_totals) are non-featured
        and must be queried one event at a time via /events/{id}/odds.
        Each call costs credits, so this is gated by alt_lines_enabled.
        Returns the same events list with alt markets appended to bookmakers.
        """
        if not self.settings.alt_lines_enabled or not events:
            return events

        cache_key = f"{sport}:odds:alt"
        cached = self.cache.get(cache_key)
        if cached is not None:
            # cached is a dict of event_id → list of (book_key, markets)
            self._merge_alt_data(events, cached)
            return events

        if not self.budget.can_fetch_odds:
            return events

        sem = asyncio.Semaphore(self.settings.props_max_concurrent)
        alt_data: dict[str, list[tuple[str, str, list]]] = {}

        async def _fetch_one(event_id: str) -> None:
            async with sem:
                try:
                    alt_event = await get_event_odds(
                        self.client,
                        sport,
                        event_id,
                        regions=self.settings.regions_str,
                        markets=ALT_MARKETS,
                        odds_format=self.settings.odds_format,
                        bookmakers=self.settings.bookmakers,
                    )
                    self._sync_budget()
                    # Store bookmaker data for merging
                    alt_data[event_id] = [
                        (bm.key, bm.title, [m.model_dump() for m in bm.markets])
                        for bm in alt_event.bookmakers
                        if bm.markets
                    ]
                except Exception:
                    log.warning("Failed to fetch alt lines for event %s", event_id)

        event_ids = [e.id for e in events]
        await asyncio.gather(*[_fetch_one(eid) for eid in event_ids])

        if alt_data:
            self.cache.set(cache_key, alt_data, ttl=self.settings.odds_refresh_interval)
            self._merge_alt_data(events, alt_data)

        return events

    @staticmethod
    def _merge_alt_data(
        events: list[Event],
        alt_data: dict[str, list[tuple[str, str, list]]],
    ) -> None:
        """Merge cached alt-line market data into existing events."""
        from app.api.models import Market

        event_map = {e.id: e for e in events}
        for event_id, book_entries in alt_data.items():
            event = event_map.get(event_id)
            if not event:
                continue
            base_books = {bm.key: bm for bm in event.bookmakers}
            for book_key, book_title, raw_markets in book_entries:
                markets = [Market(**m) for m in raw_markets]
                if book_key in base_books:
                    base_books[book_key].markets.extend(markets)
                else:
                    event.bookmakers.append(
                        Bookmaker(key=book_key, title=book_title, markets=markets)
                    )

    async def get_game_rows(self, sport: str) -> list[GameRow]:
        """Merge scores + odds into unified game rows."""
        scores = await self.fetch_scores(sport)
        events = await self.fetch_odds(sport)

        # Enrich with alt lines before building rows
        if self.settings.alt_lines_enabled:
            await self.fetch_alt_lines(sport, events)

        score_map: dict[str, Score] = {s.id: s for s in scores}
        rows: list[GameRow] = []

        seen_ids: set[str] = set()
        for event in events:
            score = score_map.get(event.id)
            rows.append(
                GameRow(
                    event_id=event.id,
                    sport_key=event.sport_key,
                    home_team=event.home_team,
                    away_team=event.away_team,
                    commence_time=event.commence_time,
                    home_score=score.home_score() if score else "-",
                    away_score=score.away_score() if score else "-",
                    completed=score.completed if score else False,
                    bookmakers=event.bookmakers,
                )
            )
            seen_ids.add(event.id)

        for score in scores:
            if score.id not in seen_ids:
                rows.append(
                    GameRow(
                        event_id=score.id,
                        sport_key=score.sport_key,
                        home_team=score.home_team,
                        away_team=score.away_team,
                        commence_time=score.commence_time,
                        home_score=score.home_score(),
                        away_score=score.away_score(),
                        completed=score.completed,
                    )
                )

        rows.sort(key=lambda r: (r.completed, r.commence_time))
        return rows

    @staticmethod
    def _filter_pre_game(events: list[Event], scores: list[Score]) -> list[Event]:
        """Filter to pre-game events only (skip live and completed)."""
        score_map = {s.id: s for s in scores}
        pre_game = []
        for e in events:
            sc = score_map.get(e.id)
            if sc is None:
                pre_game.append(e)
            elif sc.home_score() == "-" and not sc.completed:
                pre_game.append(e)
        return pre_game

    async def get_ev_bets(self, sport: str) -> list[EVBet]:
        """Find +EV bets for pre-game events only and persist to store."""
        events = await self.fetch_odds(sport)
        scores = await self.fetch_scores(sport)
        pre_game = self._filter_pre_game(events, scores)

        bets = find_ev_bets(
            pre_game,
            selected_books=self.settings.bookmakers,
            ev_threshold=self.settings.ev_threshold,
            dfs_books=self.settings.dfs_books,
            odds_range=(self.settings.ev_odds_min, self.settings.ev_odds_max),
        )

        # Persist to SQLite and deactivate bets that disappeared
        if bets:
            self.ev_store.upsert_bets(bets)
        self.ev_store.deactivate_missing(sport, bets, is_props=False)

        return bets

    def get_ev_for_sport(self, sport: str) -> list[dict]:
        """Get active EV bets for a specific sport from the store."""
        return self.ev_store.get_active_for_sport(sport, limit=40)

    # ── Arb & Middles ──

    async def get_arb_bets(self, sport: str) -> list[ArbBet]:
        """Find arbitrage opportunities for pre-game events."""
        if not self.settings.arb_enabled:
            return []
        events = await self.fetch_odds(sport)
        scores = await self.fetch_scores(sport)
        pre_game = self._filter_pre_game(events, scores)
        return find_arb_bets(
            pre_game,
            min_profit_pct=self.settings.arb_min_profit_pct,
            dfs_books=self.settings.dfs_books,
        )

    async def get_middle_bets(self, sport: str) -> list[MiddleBet]:
        """Find middle opportunities for pre-game events."""
        if not self.settings.middle_enabled:
            return []
        events = await self.fetch_odds(sport)
        scores = await self.fetch_scores(sport)
        pre_game = self._filter_pre_game(events, scores)
        return find_middle_bets(
            pre_game,
            min_window=self.settings.middle_min_window,
            max_combined_cost=self.settings.middle_max_combined_cost,
            dfs_books=self.settings.dfs_books,
        )

    # ── Props ──

    async def fetch_props(self, sport: str) -> list[Event]:
        """Fetch player-prop odds for all events in a sport."""
        if not self.budget.can_fetch_props:
            log.warning("Budget too low for props fetch")
            return self.cache.get(f"{sport}:props") or []

        cache_key = f"{sport}:props"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # Get the prop market keys for this sport
        markets = self.settings.props_markets.get(sport, [])
        if not markets:
            return []

        try:
            # Get event IDs (free endpoint)
            raw_events = await get_events(self.client, sport)
            event_ids = [e["id"] for e in raw_events]
            if not event_ids:
                return []

            events = await get_props_for_events(
                self.client,
                sport,
                event_ids,
                regions=self.settings.regions_str,
                markets=",".join(markets),
                odds_format=self.settings.odds_format,
                bookmakers=self.settings.bookmakers,
                max_concurrent=self.settings.props_max_concurrent,
            )
            self._sync_budget()
            self.cache.set(
                cache_key, events, ttl=self.settings.props_refresh_interval
            )
            return events
        except Exception:
            log.exception("Failed to fetch props for %s", sport)
            return []

    def get_prop_rows(self, events: list[Event]) -> list[PropRow]:
        """Flatten prop events into paired Over/Under PropRow list.

        Groups by (event, player, market, point) so books at different lines
        become separate rows.  DFS book odds are overridden from settings.
        """
        dfs = self.settings.dfs_books
        merged: dict[str, PropRow] = {}

        for event in events:
            for bm in event.bookmakers:
                for mkt in bm.markets:
                    for outcome in mkt.outcomes:
                        if not outcome.description:
                            continue
                        pt = outcome.point
                        pt_key = str(pt) if pt is not None else "_"
                        key = f"{event.id}|{outcome.description}|{mkt.key}|{pt_key}"
                        if key not in merged:
                            merged[key] = PropRow(
                                event_id=event.id,
                                sport_key=event.sport_key,
                                home_team=event.home_team,
                                away_team=event.away_team,
                                commence_time=event.commence_time,
                                player_name=outcome.description,
                                market_key=mkt.key,
                                consensus_point=pt,
                            )

                        row = merged[key]
                        price = dfs.get(bm.key, outcome.price)
                        if outcome.name == "Over":
                            row.over_odds[bm.key] = price
                        elif outcome.name == "Under":
                            row.under_odds[bm.key] = price

        result = list(merged.values())
        result.sort(key=lambda r: (
            r.commence_time, r.home_team, r.player_name,
            r.market_key, r.consensus_point or 0,
        ))
        return result

    async def get_prop_ev_bets(self, sport: str) -> list[EVBet]:
        """Find +EV prop bets and persist to store."""
        events = await self.fetch_props(sport)
        bets = find_ev_bets(
            events,
            selected_books=self.settings.bookmakers,
            ev_threshold=self.settings.ev_threshold,
            is_props=True,
            dfs_books=self.settings.dfs_books,
            odds_range=(self.settings.ev_odds_min, self.settings.ev_odds_max),
        )
        if bets:
            self.ev_store.upsert_bets(bets)
        self.ev_store.deactivate_missing(sport, bets, is_props=True)
        return bets

    def get_prop_ev_for_sport(self, sport: str) -> list[dict]:
        """Get active prop EV bets from the store."""
        return self.ev_store.get_active_for_sport(sport, limit=40, is_props=True)

    def force_refresh(self, sport: str) -> None:
        """Invalidate cache for a sport to force a fresh fetch."""
        self.cache.invalidate(f"{sport}:scores")
        self.cache.invalidate(f"{sport}:odds")
        self.cache.invalidate(f"{sport}:odds:alt")
        self.cache.invalidate(f"{sport}:props")
