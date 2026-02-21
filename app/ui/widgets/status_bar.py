"""Status bar: credits remaining, last refresh, warnings."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from app.services.budget import BudgetTracker


class StatusBar(Static):
    """Bottom status bar showing credits, refresh time, and warnings."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: #1a1a2e;
        color: #aaaaaa;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "[bold]Credits: --[/bold]  |  "
            "[dim]q:Quit  \u2190/\u2192:Sport  1/2/3:Market  r:Refresh  e:EV  m:Mid  t:PropMkt  p:Props  s:Settings[/dim]",
            **kwargs,
        )
        self._credits = "Credits: --"
        self._last_refresh = ""
        self._warning = ""
        self._refreshing = False

    def update_credits(self, budget: BudgetTracker) -> None:
        self._credits = budget.status_text
        self._warning = budget.warning_text
        self._refresh_content()

    def update_refresh_time(self) -> None:
        self._last_refresh = f"Last: {datetime.now().strftime('%H:%M:%S')}"
        self._refresh_content()

    def set_warning(self, text: str) -> None:
        self._warning = text
        self._refresh_content()

    def set_refreshing(self, refreshing: bool) -> None:
        self._refreshing = refreshing
        self._refresh_content()

    def _refresh_content(self) -> None:
        parts: list[str] = []
        parts.append(f"[bold]{self._credits}[/bold]")
        if self._refreshing:
            parts.append("[bold yellow]Refreshing...[/bold yellow]")
        if self._last_refresh:
            parts.append(self._last_refresh)
        if self._warning:
            parts.append(f"[bold red]{self._warning}[/bold red]")
        parts.append(
            "[dim]q:Quit  \u2190/\u2192:Sport  1/2/3:Market  "
            "f:Filter  /:Search  a:Arb  m:Mid  t:PropMkt  "
            "e:EV  l:AltLn  p:Props  r:Refresh  s:Settings[/dim]"
        )
        self.update("  |  ".join(parts))
