"""Tests for middles detection."""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.models import Bookmaker, Event, Market, OutcomeOdds
from app.services.ev import find_middle_bets


def _make_spread_middle_event() -> Event:
    """Event with a spread middle:
    Book A: Lakers -3 (-110), Celtics +3 (-110)
    Book B: Lakers -4.5 (-110), Celtics +4.5 (-110)

    Middle exists: take Celtics +4.5 at Book B, Lakers -3 at Book A
    Window = 4.5 + (-3) = 1.5 points
    """
    return Event(
        id="mid1",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="spreads", outcomes=[
                    OutcomeOdds(name="Lakers", price=-110, point=-3.0),
                    OutcomeOdds(name="Celtics", price=-110, point=3.0),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="spreads", outcomes=[
                    OutcomeOdds(name="Lakers", price=-110, point=-4.5),
                    OutcomeOdds(name="Celtics", price=-110, point=4.5),
                ]),
            ]),
        ],
    )


def _make_total_middle_event() -> Event:
    """Event with a total middle:
    Book A: Over 220.5 (-110)
    Book B: Under 222.5 (-110)
    Window = 222.5 - 220.5 = 2.0
    """
    return Event(
        id="mid2",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="totals", outcomes=[
                    OutcomeOdds(name="Over", price=-110, point=220.5),
                    OutcomeOdds(name="Under", price=-110, point=220.5),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="totals", outcomes=[
                    OutcomeOdds(name="Over", price=-110, point=222.5),
                    OutcomeOdds(name="Under", price=-110, point=222.5),
                ]),
            ]),
        ],
    )


def _make_no_middle_event() -> Event:
    """Same lines everywhere — no middle."""
    return Event(
        id="nomid",
        sport_key="basketball_nba",
        sport_title="NBA",
        commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
        home_team="Lakers",
        away_team="Celtics",
        bookmakers=[
            Bookmaker(key="book_a", title="Book A", markets=[
                Market(key="spreads", outcomes=[
                    OutcomeOdds(name="Lakers", price=-110, point=-3.5),
                    OutcomeOdds(name="Celtics", price=-110, point=3.5),
                ]),
            ]),
            Bookmaker(key="book_b", title="Book B", markets=[
                Market(key="spreads", outcomes=[
                    OutcomeOdds(name="Lakers", price=-112, point=-3.5),
                    OutcomeOdds(name="Celtics", price=-108, point=3.5),
                ]),
            ]),
        ],
    )


def test_finds_spread_middle():
    middles = find_middle_bets([_make_spread_middle_event()])
    assert len(middles) >= 1
    mid = middles[0]
    assert mid.window_size >= 0.5
    assert mid.event_id == "mid1"
    assert mid.hit_prob > 0
    assert isinstance(mid.ev_percentage, float)


def test_finds_total_middle():
    middles = find_middle_bets([_make_total_middle_event()])
    assert len(middles) >= 1
    mid = middles[0]
    assert mid.window_size == 2.0
    assert mid.event_id == "mid2"
    assert mid.hit_prob > 0
    assert isinstance(mid.ev_percentage, float)


def test_no_middle_same_lines():
    middles = find_middle_bets([_make_no_middle_event()])
    assert middles == []


def test_min_window_filter():
    middles = find_middle_bets([_make_spread_middle_event()], min_window=10.0)
    assert middles == []


def test_max_cost_filter():
    middles = find_middle_bets([_make_spread_middle_event()], max_combined_cost=0.5)
    assert middles == []


def test_sorted_by_ev():
    middles = find_middle_bets([_make_spread_middle_event()])
    if len(middles) >= 2:
        for i in range(len(middles) - 1):
            assert middles[i].ev_percentage >= middles[i + 1].ev_percentage


def test_hit_prob_scales_with_window():
    """Wider window should have higher hit probability."""
    from app.services.ev import _estimate_middle_hit_prob
    prob_small = _estimate_middle_hit_prob(1.0, "basketball_nba", "totals")
    prob_big = _estimate_middle_hit_prob(3.0, "basketball_nba", "totals")
    assert prob_big > prob_small


def test_ev_positive_with_good_odds():
    """A middle with good odds on both sides and a wide window should be +EV."""
    from app.services.ev import _compute_middle_ev, _estimate_middle_hit_prob
    hp = _estimate_middle_hit_prob(3.0, "basketball_nba", "totals")
    # Both legs at +100 (even money) with 3-point window
    ev = _compute_middle_ev(100, 100, hp)
    # With ~10.5% hit prob and even-money legs, should be positive
    assert ev > 0
