"""Tests for EVStore using in-memory SQLite."""

from __future__ import annotations

from datetime import datetime

from app.services.ev import EVBet
from app.services.ev_store import EVStore


def _make_bet(**kwargs) -> EVBet:
    defaults = {
        "sport_key": "basketball_nba",
        "book": "fanduel",
        "book_title": "FanDuel",
        "event_id": "event1",
        "home_team": "Lakers",
        "away_team": "Celtics",
        "market": "h2h",
        "outcome_name": "Lakers",
        "odds": -150.0,
        "decimal_odds": 1.667,
        "implied_prob": 0.6,
        "no_vig_prob": 0.55,
        "fair_odds": -122.0,
        "ev_percentage": 5.0,
        "edge": 0.05,
        "detected_at": datetime.now(),
        "num_books": 4,
    }
    defaults.update(kwargs)
    return EVBet(**defaults)


def test_no_drop_table_on_init():
    """Verify EVStore doesn't DROP TABLE on init (the bug fix)."""
    store = EVStore(db_path=":memory:")
    bet = _make_bet()
    store.upsert_bets([bet])

    # Create a second store on the same db — data should persist
    # (We can't share :memory: across connections, but we verify
    # the SQL doesn't contain DROP TABLE)
    import inspect
    source = inspect.getsource(store._create_tables)
    assert "DROP TABLE" not in source


def test_upsert_and_get_active():
    store = EVStore(db_path=":memory:")
    bet = _make_bet()
    store.upsert_bets([bet])

    active = store.get_active_for_sport("basketball_nba")
    assert len(active) == 1
    assert active[0]["book"] == "fanduel"
    assert active[0]["ev_percentage"] == 5.0


def test_upsert_updates_existing():
    store = EVStore(db_path=":memory:")
    bet1 = _make_bet(ev_percentage=5.0)
    store.upsert_bets([bet1])

    bet2 = _make_bet(ev_percentage=8.0)
    store.upsert_bets([bet2])

    active = store.get_active_for_sport("basketball_nba")
    assert len(active) == 1
    assert active[0]["ev_percentage"] == 8.0


def test_deactivate_missing():
    store = EVStore(db_path=":memory:")
    bet1 = _make_bet(book="fanduel")
    bet2 = _make_bet(book="draftkings")
    store.upsert_bets([bet1, bet2])

    # Only bet1 is still active
    store.deactivate_missing("basketball_nba", [bet1])
    active = store.get_active_for_sport("basketball_nba")
    assert len(active) == 1
    assert active[0]["book"] == "fanduel"


def test_deactivate_missing_empty_clears_all():
    store = EVStore(db_path=":memory:")
    store.upsert_bets([_make_bet()])
    store.deactivate_missing("basketball_nba", [])
    assert store.get_active_for_sport("basketball_nba") == []


def test_prop_scoping():
    store = EVStore(db_path=":memory:")
    game_bet = _make_bet(is_prop=False)
    prop_bet = _make_bet(
        market="player_points",
        outcome_name="Over",
        outcome_point=25.5,
        player_name="LeBron James",
        is_prop=True,
    )
    store.upsert_bets([game_bet, prop_bet])

    games = store.get_active_for_sport("basketball_nba", is_props=False)
    props = store.get_active_for_sport("basketball_nba", is_props=True)
    assert len(games) == 1
    assert len(props) == 1


def test_get_active_limit():
    store = EVStore(db_path=":memory:")
    bets = [_make_bet(book=f"book{i}") for i in range(10)]
    store.upsert_bets(bets)
    active = store.get_active_for_sport("basketball_nba", limit=3)
    assert len(active) == 3


def test_mark_stale_for_sport():
    store = EVStore(db_path=":memory:")
    bet1 = _make_bet(event_id="e1")
    bet2 = _make_bet(event_id="e2", book="draftkings")
    store.upsert_bets([bet1, bet2])

    store.mark_stale_for_sport("basketball_nba", {"e1"})
    active = store.get_active_for_sport("basketball_nba")
    assert len(active) == 1
    assert active[0]["event_id"] == "e1"


def test_close():
    store = EVStore(db_path=":memory:")
    store.close()
    # Verify it doesn't raise on close
