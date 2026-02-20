"""Full-width EV panel with clean formatting."""

from __future__ import annotations

from datetime import datetime

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


def _odds(price: float) -> str:
    return f"+{int(price)}" if price >= 0 else str(int(price))


def _mkt(market: str) -> str:
    return {"h2h": "ML", "spreads": "Sprd", "totals": "O/U"}.get(market, market)


def _ago(dt_str: str | None) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        mins = int((datetime.now() - dt).total_seconds() / 60)
        if mins < 1:
            return "now"
        if mins < 60:
            return f"{mins}m"
        return f"{mins // 60}h{mins % 60}m"
    except Exception:
        return ""


def _build_ev_header() -> Text:
    """Build EV table column headers."""
    h = Text()
    h.append("EV".rjust(7), style="bold #00ff88")
    h.append("  ")
    h.append("BOOK".ljust(14), style="bold #00ff88")
    h.append("  ")
    h.append("GAME".ljust(28), style="bold #00ff88")
    h.append("  ")
    h.append("PICK".ljust(20), style="bold #00ff88")
    h.append("  ")
    h.append("ODDS".rjust(6), style="bold #00ff88")
    h.append("  ")
    h.append("FAIR".rjust(6), style="bold #00ff88")
    h.append("  ")
    h.append("#BK".rjust(3), style="bold #00ff88")
    h.append("  ")
    h.append("AGO".ljust(5), style="bold #00ff88")
    return h


def _build_ev_row(r: dict) -> Text:
    """Build one EV bet line."""
    line = Text()

    # EV — text color only, no background
    ev = r["ev_percentage"]
    if ev >= 10:
        line.append(f"+{ev:.1f}%".rjust(7), style="bold #00ff88")
    elif ev >= 5:
        line.append(f"+{ev:.1f}%".rjust(7), style="bold green")
    else:
        line.append(f"+{ev:.1f}%".rjust(7), style="green")

    line.append("  ")

    # Book
    line.append(r["book_title"][:14].ljust(14), style="bold")

    line.append("  ")

    # Game
    away = r["away_team"][:12]
    home = r["home_team"][:12]
    line.append(f"{away} @ {home}".ljust(28), style="dim")

    line.append("  ")

    # Pick — market + outcome + point (NO odds here)
    market = _mkt(r["market"])
    outcome = r["outcome_name"][:12]
    pt = r.get("outcome_point_str", "")
    pt_str = f" {pt}" if pt else ""
    pick_str = f"{market} {outcome}{pt_str}"
    line.append(pick_str[:20].ljust(20), style="white")

    line.append("  ")

    # Odds — separate column
    line.append(_odds(r["odds"]).rjust(6), style="bold cyan")

    line.append("  ")

    # Fair
    line.append(_odds(r["fair_odds"]).rjust(6), style="white")

    line.append("  ")

    # Books
    line.append(str(r.get("num_books", 0)).rjust(3), style="dim")

    line.append("  ")

    # Ago
    line.append(_ago(r.get("detected_at")).ljust(5), style="dim")

    return line


def _build_ev_display(rows: list[dict]) -> Group:
    """Build the full EV display."""
    elements: list = [_build_ev_header(), Rule(style="#00ff88")]
    for r in rows:
        elements.append(_build_ev_row(r))
    return Group(*elements)


class EVPanel(VerticalScroll):
    """Full-width bottom panel showing +EV betting opportunities."""

    DEFAULT_CSS = """
    EVPanel {
        height: 40%;
        border-top: thick #00ff88;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #00ff88]  +EV PLAYS[/]  [dim]pre-game only · market-average no-vig fair odds[/dim]",
            id="ev-header",
        )
        yield Static("[dim]Scanning for +EV...[/dim]", id="ev-content")

    def update_from_store(self, rows: list[dict]) -> None:
        try:
            content = self.query_one("#ev-content", Static)
        except Exception:
            return

        if not rows:
            content.update("[dim]  No +EV plays detected[/dim]")
            return

        content.update(_build_ev_display(rows))

    def update_bets(self, bets: list) -> None:
        """Fallback: update directly from EVBet objects."""
        try:
            content = self.query_one("#ev-content", Static)
        except Exception:
            return
        if not bets:
            content.update("[dim]  No +EV plays detected[/dim]")
            return
        rows = []
        for bet in bets[:40]:
            rows.append({
                "ev_percentage": bet.ev_percentage,
                "book_title": bet.book_title,
                "away_team": bet.away_team,
                "home_team": bet.home_team,
                "market": bet.market,
                "outcome_name": bet.outcome_name,
                "outcome_point_str": (
                    str(bet.outcome_point) if bet.outcome_point is not None else ""
                ),
                "odds": bet.odds,
                "fair_odds": bet.fair_odds,
                "num_books": bet.num_books,
                "detected_at": (
                    bet.detected_at.isoformat() if bet.detected_at else None
                ),
            })
        content.update(_build_ev_display(rows))

    def toggle(self) -> None:
        self.display = not self.display
