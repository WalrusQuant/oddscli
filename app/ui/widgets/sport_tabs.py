"""Horizontal sport navigation bar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


SPORT_LABELS: dict[str, str] = {
    "americanfootball_nfl": "NFL",
    "americanfootball_ncaaf": "NCAAF",
    "basketball_nba": "NBA",
    "basketball_ncaab": "NCAAB",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "soccer_epl": "EPL",
    "soccer_usa_mls": "MLS",
    "mma_mixed_martial_arts": "MMA",
    "tennis_atp_french_open": "Tennis",
}


class SportTabs(Widget):
    """Tab bar for switching between sports."""

    DEFAULT_CSS = """
    SportTabs {
        height: 3;
        dock: top;
    }
    """

    active_index: reactive[int] = reactive(0)

    class Changed(Message):
        def __init__(self, sport_key: str) -> None:
            super().__init__()
            self.sport_key = sport_key

    def __init__(self, sports: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.sports = sports

    def _label(self, sport_key: str) -> str:
        return SPORT_LABELS.get(sport_key, sport_key.split("_")[-1].upper())

    def compose(self) -> ComposeResult:
        yield Static(id="sport-tabs-content")

    def on_mount(self) -> None:
        self._render_tabs()

    def watch_active_index(self, _old: int, _new: int) -> None:
        self._render_tabs()
        if self.sports:
            self.post_message(self.Changed(self.sports[self._clamped_index]))

    @property
    def _clamped_index(self) -> int:
        if not self.sports:
            return 0
        return max(0, min(self.active_index, len(self.sports) - 1))

    @property
    def current_sport(self) -> str:
        if not self.sports:
            return ""
        return self.sports[self._clamped_index]

    def _render_tabs(self) -> None:
        parts: list[str] = []
        for i, sport in enumerate(self.sports):
            label = self._label(sport)
            if i == self._clamped_index:
                parts.append(f"[bold white on #333333] {label} [/]")
            else:
                parts.append(f"[dim] {label} [/]")
        content = self.query_one("#sport-tabs-content", Static)
        content.update("  ".join(parts))

    def next_sport(self) -> None:
        if self.sports:
            self.active_index = (self._clamped_index + 1) % len(self.sports)

    def prev_sport(self) -> None:
        if self.sports:
            self.active_index = (self._clamped_index - 1) % len(self.sports)

    def set_sports(self, sports: list[str]) -> None:
        """Replace the sports list (e.g. after filtering out off-season)."""
        self.sports = sports
        self.active_index = 0
        self._render_tabs()
