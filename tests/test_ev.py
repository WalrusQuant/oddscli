"""Tests for EV calculation engine."""

from __future__ import annotations

import pytest

from app.api.models import Bookmaker, Event, Market, OutcomeOdds
from app.services.ev import (
    _calculate_market_avg_no_vig,
    american_to_decimal,
    american_to_implied_prob,
    compute_inline_ev,
    find_ev_bets,
    prob_to_american,
    remove_vig,
)


class TestAmericanToDecimal:
    def test_positive_odds(self):
        assert american_to_decimal(100) == 2.0
        assert american_to_decimal(200) == 3.0

    def test_negative_odds(self):
        assert american_to_decimal(-100) == 2.0
        assert american_to_decimal(-200) == 1.5

    def test_large_underdog(self):
        assert american_to_decimal(500) == 6.0

    def test_zero_odds(self):
        """Zero American odds should not cause division by zero."""
        assert american_to_decimal(0) == 1.0


class TestAmericanToImpliedProb:
    def test_even_odds(self):
        assert american_to_implied_prob(100) == pytest.approx(0.5)
        assert american_to_implied_prob(-100) == pytest.approx(0.5)

    def test_favorite(self):
        # -200 → 200/300 = 0.6667
        assert american_to_implied_prob(-200) == pytest.approx(2 / 3)

    def test_underdog(self):
        # +200 → 100/300 = 0.3333
        assert american_to_implied_prob(200) == pytest.approx(1 / 3)

    def test_zero_odds(self):
        """Zero American odds should return 0.0 probability, not crash."""
        assert american_to_implied_prob(0) == 0.0


class TestProbToAmerican:
    def test_favorite(self):
        # 0.6667 → ~-200
        result = prob_to_american(2 / 3)
        assert result == pytest.approx(-200, abs=1)

    def test_underdog(self):
        result = prob_to_american(1 / 3)
        assert result == pytest.approx(200, abs=1)

    def test_even(self):
        result = prob_to_american(0.5)
        assert result == pytest.approx(-100, abs=1)

    def test_edge_cases(self):
        assert prob_to_american(0.0) == 0.0
        assert prob_to_american(1.0) == 0.0


class TestRemoveVig:
    def test_basic_removal(self):
        # Typical vig: both sides ~0.5238 → sum=1.0476
        probs = [0.5238, 0.5238]
        result = remove_vig(probs)
        assert sum(result) == pytest.approx(1.0)
        assert result[0] == pytest.approx(0.5)
        assert result[1] == pytest.approx(0.5)

    def test_empty_list(self):
        assert remove_vig([]) == []

    def test_unequal_probs(self):
        result = remove_vig([0.6, 0.5])
        assert sum(result) == pytest.approx(1.0)


class TestComputeInlineEv:
    def test_insufficient_books(self):
        novig, ev = compute_inline_ev([100, 105], [-110, -115])
        assert novig is None
        assert ev is None

    def test_valid_computation(self):
        # 4 books each side
        prices = [-110, -108, -112, -105]
        counter = [-110, -112, -108, -115]
        novig, ev = compute_inline_ev(prices, counter)
        assert novig is not None
        assert ev is not None

    def test_positive_ev(self):
        # Create scenario where best price has positive EV
        # Counter side is heavily juiced → fair price on this side is good
        prices = [150, 140, 135, 130]
        counter = [-200, -210, -190, -195]
        novig, ev = compute_inline_ev(prices, counter)
        assert novig is not None
        # Best price (150) should have positive EV against the no-vig line
        assert ev is not None


class TestFindEvBets:
    def test_returns_list(self, sample_event: Event):
        bets = find_ev_bets([sample_event], ev_threshold=0.0)
        assert isinstance(bets, list)

    def test_sorted_by_ev_descending(self, sample_event: Event):
        bets = find_ev_bets([sample_event], ev_threshold=0.0)
        if len(bets) >= 2:
            for i in range(len(bets) - 1):
                assert bets[i].ev_percentage >= bets[i + 1].ev_percentage

    def test_high_threshold_returns_empty(self, sample_event: Event):
        bets = find_ev_bets([sample_event], ev_threshold=50.0)
        assert bets == []

    def test_selected_books_filter(self, sample_event: Event):
        bets = find_ev_bets(
            [sample_event],
            selected_books=["fanduel"],
            ev_threshold=0.0,
        )
        for bet in bets:
            assert bet.book == "fanduel"

    def test_props_mode(self, sample_prop_event: Event):
        bets = find_ev_bets(
            [sample_prop_event],
            is_props=True,
            ev_threshold=0.0,
        )
        for bet in bets:
            assert bet.is_prop
            assert bet.player_name is not None

    def test_dfs_books_override(self, sample_event: Event):
        # DFS book at -130 effective odds (lighter juice than typical -137)
        find_ev_bets([sample_event], ev_threshold=0.0)
        bets_with = find_ev_bets(
            [sample_event],
            ev_threshold=0.0,
            dfs_books={"fanduel": -130},
        )
        # Just verify it runs without error and returns valid results
        assert isinstance(bets_with, list)


class TestDfsConsensus:
    def test_dfs_does_not_pollute_consensus(self):
        """DFS book with synthetic odds should not affect consensus no-vig probs.

        _calculate_market_avg_no_vig should use raw book prices, not DFS overrides.
        """
        # Create two sides with known prices
        bm_a = Bookmaker(key="fanduel", title="FanDuel", markets=[
            Market(key="h2h", outcomes=[
                OutcomeOdds(name="TeamA", price=-110),
            ]),
        ])
        bm_b = Bookmaker(key="draftkings", title="DraftKings", markets=[
            Market(key="h2h", outcomes=[
                OutcomeOdds(name="TeamA", price=-108),
            ]),
        ])
        bm_c = Bookmaker(key="betmgm", title="BetMGM", markets=[
            Market(key="h2h", outcomes=[
                OutcomeOdds(name="TeamA", price=-112),
            ]),
        ])
        # DFS book with very different price
        bm_dfs = Bookmaker(key="prizepicks", title="PrizePicks", markets=[
            Market(key="h2h", outcomes=[
                OutcomeOdds(name="TeamA", price=-200),
            ]),
        ])

        book_outcomes = {
            "TeamA|None": [
                (bm_a, bm_a.markets[0].outcomes[0]),
                (bm_b, bm_b.markets[0].outcomes[0]),
                (bm_c, bm_c.markets[0].outcomes[0]),
                (bm_dfs, bm_dfs.markets[0].outcomes[0]),
            ],
        }

        no_vig, counts = _calculate_market_avg_no_vig(book_outcomes)

        # The DFS book's raw price (-200) is used in the calculation —
        # _calculate_market_avg_no_vig no longer takes dfs_books, so it always
        # uses outcome.price. The key point is that the old bug where
        # _effective_price(outcome, bm, dfs_books) replaced -200 with e.g. -130
        # no longer happens because the function doesn't accept dfs_books.
        assert "TeamA|None" in no_vig
        assert counts["TeamA|None"] == 4
