"""Tests for API models."""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.models import GameRow, PropRow, Score, ScoreValue


class TestScore:
    def test_home_score_with_data(self, sample_score):
        assert sample_score.home_score() == "55"

    def test_away_score_with_data(self, sample_score):
        assert sample_score.away_score() == "52"

    def test_home_score_no_scores(self):
        score = Score(
            id="s1",
            sport_key="basketball_nba",
            commence_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            home_team="Lakers",
            away_team="Celtics",
        )
        assert score.home_score() == "-"

    def test_away_score_no_scores(self):
        score = Score(
            id="s1",
            sport_key="basketball_nba",
            commence_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            home_team="Lakers",
            away_team="Celtics",
        )
        assert score.away_score() == "-"

    def test_score_with_null_value(self):
        score = Score(
            id="s1",
            sport_key="basketball_nba",
            commence_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            home_team="Lakers",
            away_team="Celtics",
            scores=[ScoreValue(name="Lakers", score=None)],
        )
        assert score.home_score() == "-"


class TestGameRow:
    def test_default_scores(self):
        row = GameRow(
            event_id="e1",
            sport_key="basketball_nba",
            home_team="Lakers",
            away_team="Celtics",
            commence_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert row.home_score == "-"
        assert row.away_score == "-"
        assert row.completed is False
        assert row.bookmakers == []


class TestPropRow:
    def test_default_odds(self):
        row = PropRow(
            event_id="e1",
            sport_key="basketball_nba",
            home_team="Lakers",
            away_team="Celtics",
            commence_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            player_name="LeBron James",
            market_key="player_points",
        )
        assert row.over_odds == {}
        assert row.under_odds == {}
        assert row.consensus_point is None
