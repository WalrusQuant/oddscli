"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.models import Bookmaker, Event, Market, OutcomeOdds, Score, ScoreValue


@pytest.fixture
def sample_event() -> Event:
    """A pre-game event with 4 books offering h2h, spreads, totals."""
    return Event(
        id="event1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            _make_bookmaker("fanduel", "FanDuel", home=-150, away=130, spread_home=-3.5, spread_away=3.5, spread_home_price=-110, spread_away_price=-110, total=220.5, over_price=-110, under_price=-110),
            _make_bookmaker("draftkings", "DraftKings", home=-145, away=125, spread_home=-3.5, spread_away=3.5, spread_home_price=-108, spread_away_price=-112, total=220.5, over_price=-108, under_price=-112),
            _make_bookmaker("betmgm", "BetMGM", home=-155, away=135, spread_home=-3.5, spread_away=3.5, spread_home_price=-112, spread_away_price=-108, total=220.5, over_price=-112, under_price=-108),
            _make_bookmaker("betrivers", "BetRivers", home=-148, away=128, spread_home=-3.5, spread_away=3.5, spread_home_price=-110, spread_away_price=-110, total=220.5, over_price=-105, under_price=-115),
        ],
    )


@pytest.fixture
def sample_score() -> Score:
    """A live score for the sample event."""
    return Score(
        id="event1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        completed=False,
        scores=[
            ScoreValue(name="Lakers", score="55"),
            ScoreValue(name="Celtics", score="52"),
        ],
    )


@pytest.fixture
def sample_prop_event() -> Event:
    """An event with player prop markets (4 books)."""
    return Event(
        id="event2",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            _make_prop_bookmaker("fanduel", "FanDuel", "LeBron James", 25.5, -110, -110),
            _make_prop_bookmaker("draftkings", "DraftKings", "LeBron James", 25.5, -108, -112),
            _make_prop_bookmaker("betmgm", "BetMGM", "LeBron James", 25.5, -105, -115),
            _make_prop_bookmaker("betrivers", "BetRivers", "LeBron James", 25.5, -112, -108),
        ],
    )


def _make_bookmaker(
    key: str, title: str,
    home: float, away: float,
    spread_home: float, spread_away: float,
    spread_home_price: float, spread_away_price: float,
    total: float, over_price: float, under_price: float,
) -> Bookmaker:
    return Bookmaker(
        key=key,
        title=title,
        markets=[
            Market(key="h2h", outcomes=[
                OutcomeOdds(name="Lakers", price=home),
                OutcomeOdds(name="Celtics", price=away),
            ]),
            Market(key="spreads", outcomes=[
                OutcomeOdds(name="Lakers", price=spread_home_price, point=spread_home),
                OutcomeOdds(name="Celtics", price=spread_away_price, point=spread_away),
            ]),
            Market(key="totals", outcomes=[
                OutcomeOdds(name="Over", price=over_price, point=total),
                OutcomeOdds(name="Under", price=under_price, point=total),
            ]),
        ],
    )


def _make_prop_bookmaker(
    key: str, title: str, player: str, line: float,
    over_price: float, under_price: float,
) -> Bookmaker:
    return Bookmaker(
        key=key,
        title=title,
        markets=[
            Market(key="player_points", outcomes=[
                OutcomeOdds(name="Over", price=over_price, point=line, description=player),
                OutcomeOdds(name="Under", price=under_price, point=line, description=player),
            ]),
        ],
    )
