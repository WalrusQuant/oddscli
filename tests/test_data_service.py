"""Tests for DataService with injected mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.services.budget import BudgetTracker
from app.services.cache import TTLCache
from app.services.data_service import DataService
from app.services.ev_store import EVStore


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key="test_key",
        bookmakers=["fanduel", "draftkings"],
        ev_threshold=2.0,
    )


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.last_credit_info = type("CI", (), {"remaining": 500, "used": 100})()
    return client


@pytest.fixture
def data_service(settings, mock_client):
    cache = TTLCache()
    budget = BudgetTracker()
    ev_store = EVStore(db_path=":memory:")
    return DataService(
        settings=settings,
        client=mock_client,
        cache=cache,
        budget=budget,
        ev_store=ev_store,
    )


async def test_get_game_rows_merges_scores_and_odds(data_service, sample_event, sample_score):
    """Test that game rows merge scores with odds events."""
    with patch("app.services.data_service.get_scores", new_callable=AsyncMock) as mock_scores, \
         patch("app.services.data_service.get_odds", new_callable=AsyncMock) as mock_odds:
        mock_scores.return_value = [sample_score]
        mock_odds.return_value = [sample_event]

        rows = await data_service.get_game_rows("basketball_nba")
        assert len(rows) == 1
        assert rows[0].home_team == "Lakers"
        assert rows[0].home_score == "55"
        assert rows[0].away_score == "52"


async def test_get_game_rows_score_only(data_service, sample_score):
    """Score with no matching event still shows up."""
    with patch("app.services.data_service.get_scores", new_callable=AsyncMock) as mock_scores, \
         patch("app.services.data_service.get_odds", new_callable=AsyncMock) as mock_odds:
        mock_scores.return_value = [sample_score]
        mock_odds.return_value = []  # No odds

        rows = await data_service.get_game_rows("basketball_nba")
        assert len(rows) == 1
        assert rows[0].home_score == "55"


async def test_budget_gates_odds_fetch(data_service):
    """When budget is low, odds fetch should use cache."""
    data_service.budget.update(remaining=5, used=None)
    data_service.cache.set("basketball_nba:odds", [], ttl=600)
    data_service.cache.set("basketball_nba:scores", [], ttl=600)

    rows = await data_service.get_game_rows("basketball_nba")
    assert rows == []


async def test_budget_allows_scores_when_low(data_service, sample_score):
    """When budget is low but not critical, scores should still be fetched."""
    data_service.budget.update(remaining=30, used=None)

    with patch("app.services.data_service.get_scores", new_callable=AsyncMock) as mock_scores, \
         patch("app.services.data_service.get_odds", new_callable=AsyncMock) as mock_odds:
        mock_scores.return_value = [sample_score]
        mock_odds.return_value = []  # Budget too low for odds

        # Scores should still go through
        rows = await data_service.get_game_rows("basketball_nba")
        assert len(rows) == 1


async def test_force_refresh_invalidates_cache(data_service):
    data_service.cache.set("basketball_nba:scores", [1], ttl=60)
    data_service.cache.set("basketball_nba:odds", [2], ttl=60)
    data_service.cache.set("basketball_nba:props", [3], ttl=60)

    data_service.force_refresh("basketball_nba")

    assert data_service.cache.get("basketball_nba:scores") is None
    assert data_service.cache.get("basketball_nba:odds") is None
    assert data_service.cache.get("basketball_nba:props") is None
