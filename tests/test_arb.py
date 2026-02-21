"""Tests for arbitrage detection."""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.models import Bookmaker, Event, Market, OutcomeOdds
from app.services.ev import find_arb_bets


def _make_arb_event() -> Event:
    """Event with an arb: Book A has team1 at +200, Book B has team2 at +200.
    Implied: 0.333 + 0.333 = 0.667 < 1.0 → guaranteed profit.
    """
    return Event(
        id="arb1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="h2h", outcomes=[
                    OutcomeOdds(name="Lakers", price=200),
                    OutcomeOdds(name="Celtics", price=-300),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="h2h", outcomes=[
                    OutcomeOdds(name="Lakers", price=-300),
                    OutcomeOdds(name="Celtics", price=200),
                ]),
            ]),
        ],
    )


def _make_no_arb_event() -> Event:
    """Event with normal vig — no arb."""
    return Event(
        id="noarb1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="h2h", outcomes=[
                    OutcomeOdds(name="Lakers", price=-110),
                    OutcomeOdds(name="Celtics", price=-110),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="h2h", outcomes=[
                    OutcomeOdds(name="Lakers", price=-110),
                    OutcomeOdds(name="Celtics", price=-110),
                ]),
            ]),
        ],
    )


def test_finds_arb():
    arbs = find_arb_bets([_make_arb_event()])
    assert len(arbs) >= 1
    arb = arbs[0]
    assert arb.profit_pct > 0
    assert arb.implied_sum < 1.0
    assert arb.event_id == "arb1"


def test_no_arb_when_juiced():
    arbs = find_arb_bets([_make_no_arb_event()])
    assert arbs == []


def test_arb_sorted_by_profit():
    arbs = find_arb_bets([_make_arb_event()])
    if len(arbs) >= 2:
        for i in range(len(arbs) - 1):
            assert arbs[i].profit_pct >= arbs[i + 1].profit_pct


def test_min_profit_filter():
    arbs = find_arb_bets([_make_arb_event()], min_profit_pct=50.0)
    # Even the best arb here shouldn't hit 50%
    # (depends on the odds but likely filters most out)
    # Just verify it runs and returns valid results
    for arb in arbs:
        assert arb.profit_pct >= 50.0


def _make_cross_line_totals_event() -> Event:
    """Event where different books have different total lines.

    Book A: Over 235.5 +108 / Under 235.5 -128
    Book B: Over 231.5 -128 / Under 231.5 +108

    Over 235.5 and Under 231.5 are NOT mutually exclusive — both can lose
    (e.g., if the total is 233). This is a middle, not an arb.
    """
    return Event(
        id="crossline1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Bulls",
        away_team="Pistons",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="totals", outcomes=[
                    OutcomeOdds(name="Over", price=108, point=235.5),
                    OutcomeOdds(name="Under", price=-128, point=235.5),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="totals", outcomes=[
                    OutcomeOdds(name="Over", price=-128, point=231.5),
                    OutcomeOdds(name="Under", price=108, point=231.5),
                ]),
            ]),
        ],
    )


def test_cross_line_totals_not_arb():
    """Cross-line Over/Under at different points must NOT be flagged as arbs."""
    arbs = find_arb_bets([_make_cross_line_totals_event()])
    assert arbs == []


def _make_same_line_total_arb_event() -> Event:
    """Both books at the same total but with odds that create an arb."""
    return Event(
        id="sameline1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Bulls",
        away_team="Pistons",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="totals", outcomes=[
                    OutcomeOdds(name="Over", price=200, point=220.5),
                    OutcomeOdds(name="Under", price=-300, point=220.5),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="totals", outcomes=[
                    OutcomeOdds(name="Over", price=-300, point=220.5),
                    OutcomeOdds(name="Under", price=200, point=220.5),
                ]),
            ]),
        ],
    )


def test_same_line_total_is_arb():
    """Same-line Over/Under with inverted prices IS a true arb."""
    arbs = find_arb_bets([_make_same_line_total_arb_event()])
    assert len(arbs) >= 1
    arb = arbs[0]
    assert arb.point_a == arb.point_b or (
        # Over 220.5 and Under 220.5 — points are the same
        abs((arb.point_a or 0)) == abs((arb.point_b or 0))
    )
