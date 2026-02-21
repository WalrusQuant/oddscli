"""Middles (cross-line) opportunities panel."""

from __future__ import annotations

from rich.console import Group
from rich.rule import Rule
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from app.services.ev import MiddleBet, american_to_decimal
from app.ui.widgets.constants import PROP_LABELS, trunc

BASE_STAKE = 100.0  # Leg A fixed wager


def _odds(price: float) -> str:
    return f"+{int(price)}" if price >= 0 else str(int(price))


def _mkt(market: str) -> str:
    base = {"h2h": "ML", "spreads": "Sprd", "totals": "O/U"}
    return base.get(market, PROP_LABELS.get(market, market[:5]))


def _build_mid_header() -> Text:
    h = Text()
    h.append("EV%".rjust(7), style="bold #cc88ff")
    h.append("  ")
    h.append("HIT%".rjust(5), style="bold #cc88ff")
    h.append("  ")
    h.append("WIN".rjust(4), style="bold #cc88ff")
    h.append("  ")
    h.append("GAME".ljust(26), style="bold #cc88ff")
    h.append("  ")
    h.append("MKT".ljust(5), style="bold #cc88ff")
    h.append("  ")
    h.append("LEG A".ljust(26), style="bold #cc88ff")
    h.append("  ")
    h.append("LEG B".ljust(26), style="bold #cc88ff")
    h.append("  ")
    h.append("COST".rjust(5), style="bold #cc88ff")
    h.append("  ")
    h.append("BET A".rjust(7), style="bold #cc88ff")
    h.append("  ")
    h.append("BET B".rjust(7), style="bold #cc88ff")
    h.append("  ")
    h.append("HIT$".rjust(8), style="bold #cc88ff")
    h.append("  ")
    h.append("MISS$".rjust(8), style="bold #cc88ff")
    return h


def _compute_middle_sizing(mid: MiddleBet) -> tuple[float, float, float, float]:
    """Compute recommended bets with leg A = $100.

    Bets are equalized so the miss payout is the same regardless of
    which leg wins.

    Returns (bet_a, bet_b, hit_profit, miss_profit).
    """
    dec_a = american_to_decimal(mid.odds_a)
    dec_b = american_to_decimal(mid.odds_b)
    bet_a = BASE_STAKE
    bet_b = (bet_a * dec_a) / dec_b
    total = bet_a + bet_b
    # Hit: both legs win
    hit_profit = bet_a * dec_a + bet_b * dec_b - total
    # Miss: one wins, one loses (equalized so payout is same either way)
    miss_profit = bet_a * dec_a - total
    return bet_a, bet_b, hit_profit, miss_profit


def _build_mid_row(mid: MiddleBet) -> Text:
    line = Text()

    # EV%
    ev = mid.ev_percentage
    if ev > 0:
        line.append(f"+{ev:.1f}%".rjust(7), style="bold #cc88ff")
    else:
        line.append(f"{ev:.1f}%".rjust(7), style="dim")
    line.append("  ")

    # Hit probability
    line.append(f"{mid.hit_prob * 100:.0f}%".rjust(5), style="white")
    line.append("  ")

    # Window size
    line.append(f"{mid.window_size:.1f}".rjust(4), style="bold #cc88ff")
    line.append("  ")

    # Game / Player
    if mid.is_prop and mid.player_name:
        game_str = trunc(mid.player_name, 26)
    else:
        game_str = f"{mid.away_team[:11]} @ {mid.home_team[:11]}"
    line.append(trunc(game_str, 26), style="dim")
    line.append("  ")

    # Market
    line.append(_mkt(mid.market).ljust(5), style="white")
    line.append("  ")

    # Leg A (book + line + odds)
    leg_a = f"{mid.book_a_title[:6]} {mid.outcome_a[:5]} {mid.line_a:g} {_odds(mid.odds_a)}"
    line.append(trunc(leg_a, 26), style="cyan")
    line.append("  ")

    # Leg B (book + line + odds)
    leg_b = f"{mid.book_b_title[:6]} {mid.outcome_b[:5]} {mid.line_b:g} {_odds(mid.odds_b)}"
    line.append(trunc(leg_b, 26), style="cyan")
    line.append("  ")

    # Cost
    line.append(f"{mid.combined_cost:.2f}".rjust(5), style="dim")
    line.append("  ")

    # Bet sizing
    bet_a, bet_b, hit_profit, miss_profit = _compute_middle_sizing(mid)
    line.append(f"${bet_a:.0f}".rjust(7), style="white")
    line.append("  ")
    line.append(f"${bet_b:.2f}".rjust(7), style="white")
    line.append("  ")
    line.append(f"+${hit_profit:.2f}".rjust(8), style="bold #00ff00")
    line.append("  ")
    miss_style = "bold #00ff00" if miss_profit >= 0 else "#ff6666"
    miss_str = f"+${miss_profit:.2f}" if miss_profit >= 0 else f"-${abs(miss_profit):.2f}"
    line.append(miss_str.rjust(8), style=miss_style)

    return line


def _build_mid_display(middles: list[MiddleBet]) -> Group:
    elements: list = [_build_mid_header(), Rule(style="#cc88ff")]
    for mid in middles:
        elements.append(_build_mid_row(mid))
    return Group(*elements)


class MiddlesPanel(VerticalScroll):
    """Panel showing middle (cross-line) opportunities."""

    DEFAULT_CSS = """
    MiddlesPanel {
        height: auto;
        max-height: 30%;
        min-height: 5;
        border-top: thick #cc88ff;
        padding: 0 1;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #cc88ff]  MIDDLES[/]  "
            "[dim]cross-line opportunities · sorted by EV% · hit% is estimated[/dim]",
            id="mid-header",
        )
        yield Static("[dim]Scanning for middles...[/dim]", id="mid-content")

    def update_middles(self, middles: list[MiddleBet]) -> None:
        try:
            content = self.query_one("#mid-content", Static)
        except Exception:
            return

        if not middles:
            content.update("[dim]  No middle opportunities detected[/dim]")
            return

        content.update(_build_mid_display(middles))

    def toggle(self) -> None:
        self.display = not self.display
