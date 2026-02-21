"""Tests for BudgetTracker."""

from app.services.budget import BudgetTracker


def test_initial_state():
    bt = BudgetTracker()
    assert bt.remaining is None
    assert bt.used is None
    assert not bt.is_low
    assert not bt.is_critical
    assert bt.can_fetch_odds
    assert bt.can_fetch_scores
    assert bt.can_fetch_props


def test_update():
    bt = BudgetTracker()
    bt.update(remaining=100, used=400)
    assert bt.remaining == 100
    assert bt.used == 400


def test_low_threshold():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=50, used=None)
    assert bt.is_low
    assert not bt.is_critical


def test_critical_threshold():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=10, used=None)
    assert bt.is_low
    assert bt.is_critical


def test_can_fetch_odds_blocks_when_low():
    """Odds fetches should be blocked when credits are low."""
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=50, used=None)
    assert not bt.can_fetch_odds


def test_can_fetch_odds_allows_above_low():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=51, used=None)
    assert bt.can_fetch_odds


def test_can_fetch_scores_allowed_when_low():
    """Scores should still be fetchable when low (but not critical)."""
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=30, used=None)
    assert bt.is_low
    assert not bt.is_critical
    assert bt.can_fetch_scores


def test_can_fetch_scores_blocked_when_critical():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=10, used=None)
    assert bt.is_critical
    assert not bt.can_fetch_scores


def test_can_fetch_props_higher_threshold():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    # Props need > 3x critical (> 30)
    bt.update(remaining=31, used=None)
    assert bt.can_fetch_props
    bt.update(remaining=30, used=None)
    assert not bt.can_fetch_props


def test_status_text_unknown():
    bt = BudgetTracker()
    assert bt.status_text == "Credits: --"


def test_status_text_known():
    bt = BudgetTracker()
    bt.update(remaining=250, used=None)
    assert bt.status_text == "Credits: 250"


def test_warning_text_critical():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=5, used=None)
    assert "CRITICAL" in bt.warning_text


def test_warning_text_low():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=30, used=None)
    assert "low" in bt.warning_text.lower()


def test_warning_text_normal():
    bt = BudgetTracker(low_warning=50, critical_stop=10)
    bt.update(remaining=100, used=None)
    assert bt.warning_text == ""


def test_update_monotonic_remaining():
    """Out-of-order responses should not increase remaining credits."""
    bt = BudgetTracker()
    bt.update(remaining=100, used=None)
    assert bt.remaining == 100
    # Stale response with higher remaining should be ignored
    bt.update(remaining=150, used=None)
    assert bt.remaining == 100
    # Lower remaining should be accepted
    bt.update(remaining=90, used=None)
    assert bt.remaining == 90


def test_update_monotonic_used():
    """Out-of-order responses should not decrease used credits."""
    bt = BudgetTracker()
    bt.update(remaining=None, used=400)
    assert bt.used == 400
    # Stale response with lower used should be ignored
    bt.update(remaining=None, used=350)
    assert bt.used == 400
    # Higher used should be accepted
    bt.update(remaining=None, used=410)
    assert bt.used == 410
