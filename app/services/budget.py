"""Credit budget tracker from response headers."""

from __future__ import annotations


class BudgetTracker:
    """Tracks API credit usage from response headers."""

    def __init__(self, low_warning: int = 50, critical_stop: int = 10) -> None:
        self.remaining: int | None = None
        self.used: int | None = None
        self.low_warning = low_warning
        self.critical_stop = critical_stop

    def update(self, remaining: int | None, used: int | None) -> None:
        if remaining is not None:
            if self.remaining is None or remaining <= self.remaining:
                self.remaining = remaining
        if used is not None:
            if self.used is None or used >= self.used:
                self.used = used

    @property
    def is_low(self) -> bool:
        if self.remaining is None:
            return False
        return self.remaining <= self.low_warning

    @property
    def is_critical(self) -> bool:
        if self.remaining is None:
            return False
        return self.remaining <= self.critical_stop

    @property
    def can_fetch_odds(self) -> bool:
        """Whether we have enough credits for an odds fetch. Blocks when low."""
        if self.remaining is None:
            return True  # Unknown budget, allow
        return not self.is_low

    @property
    def can_fetch_scores(self) -> bool:
        """Scores allowed when low, blocked only when critical."""
        if self.remaining is None:
            return True
        return not self.is_critical

    @property
    def can_fetch_props(self) -> bool:
        """Props require multiple per-event calls — use a higher threshold."""
        if self.remaining is None:
            return True
        return self.remaining > self.critical_stop * 3

    @property
    def status_text(self) -> str:
        if self.remaining is None:
            return "Credits: --"
        return f"Credits: {self.remaining}"

    @property
    def warning_text(self) -> str:
        if self.is_critical:
            return "CREDITS CRITICAL - Pausing all API calls"
        if self.is_low:
            return "Credits low - Scores only mode"
        return ""
