"""Arbitrage opportunities panel."""

from __future__ import annotations

from rich.console import Group
from rich.rule import Rule
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from app.services.ev import ArbBet, american_to_decimal
from app.ui.widgets.constants import PROP_LABELS, trunc

BASE_STAKE = 100.0  # Leg A fixed wager


def _odds(price: float) -> str:
    return f"+{int(round(price))}" if price >= 0 else str(int(round(price)))


def _build_arb_header() -> Text:
    h = Text()
    h.append("PROFIT".rjust(8), style="bold #ffcc00")
    h.append("  ")
    h.append("BOOK A".ljust(10), style="bold #ffcc00")
    h.append("  ")
    h.append("BOOK B".ljust(10), style="bold #ffcc00")
    h.append("  ")
    h.append("GAME".ljust(26), style="bold #ffcc00")
    h.append("  ")
    h.append("MKT".ljust(5), style="bold #ffcc00")
    h.append("  ")
    h.append("LEG A".ljust(20), style="bold #ffcc00")
    h.append("  ")
    h.append("LEG B".ljust(20), style="bold #ffcc00")
    h.append("  ")
    h.append("BET A".rjust(7), style="bold #ffcc00")
    h.append("  ")
    h.append("BET B".rjust(9), style="bold #ffcc00")
    h.append("  ")
    h.append("PAYOUT".rjust(9), style="bold #ffcc00")
    h.append("  ")
    h.append("PROFIT$".rjust(8), style="bold #ffcc00")
    return h


def _mkt(market: str) -> str:
    base = {"h2h": "ML", "spreads": "Sprd", "totals": "O/U"}
    return base.get(market, PROP_LABELS.get(market, market[:5]))


def _compute_bet_sizing(arb: ArbBet) -> tuple[float, float, float, float]:
    """Compute recommended bets with leg A = $100.

    Returns (bet_a, bet_b, payout, profit_dollars).
    """
    dec_a = american_to_decimal(arb.odds_a)
    dec_b = american_to_decimal(arb.odds_b)
    bet_a = BASE_STAKE
    bet_b = (bet_a * dec_a) / dec_b
    payout = bet_a * dec_a  # guaranteed payout (same either side)
    profit = payout - (bet_a + bet_b)
    return bet_a, bet_b, payout, profit


def _build_arb_row(arb: ArbBet) -> Text:
    line = Text()

    # Profit %
    line.append(f"+{arb.profit_pct:.2f}%".rjust(8), style="bold #ffcc00")
    line.append("  ")

    # Book A
    line.append(trunc(arb.book_a_title, 10), style="bold")
    line.append("  ")

    # Book B
    line.append(trunc(arb.book_b_title, 10), style="bold")
    line.append("  ")

    # Game / Player
    if arb.is_prop and arb.player_name:
        game_str = trunc(arb.player_name, 26)
    else:
        game_str = f"{arb.away_team[:11]} @ {arb.home_team[:11]}"
    line.append(trunc(game_str, 26), style="dim")
    line.append("  ")

    # Market
    line.append(_mkt(arb.market).ljust(5), style="white")
    line.append("  ")

    # Leg A
    pt_a = f" {arb.point_a}" if arb.point_a is not None else ""
    leg_a = f"{arb.outcome_a[:8]}{pt_a} {_odds(arb.odds_a)}"
    line.append(trunc(leg_a, 20), style="cyan")
    line.append("  ")

    # Leg B
    pt_b = f" {arb.point_b}" if arb.point_b is not None else ""
    leg_b = f"{arb.outcome_b[:8]}{pt_b} {_odds(arb.odds_b)}"
    line.append(trunc(leg_b, 20), style="cyan")
    line.append("  ")

    # Bet sizing
    bet_a, bet_b, payout, profit = _compute_bet_sizing(arb)
    line.append(f"${bet_a:.0f}".rjust(7), style="white")
    line.append("  ")
    line.append(f"${bet_b:.2f}".rjust(9), style="white")
    line.append("  ")
    line.append(f"${payout:.2f}".rjust(9), style="bold #00ff00")
    line.append("  ")
    line.append(f"${profit:.2f}".rjust(8), style="bold #00ff00")

    return line


def _build_arb_display(arbs: list[ArbBet]) -> Group:
    elements: list = [_build_arb_header(), Rule(style="#ffcc00")]
    for arb in arbs:
        elements.append(_build_arb_row(arb))
    return Group(*elements)


class ArbPanel(VerticalScroll):
    """Panel showing arbitrage opportunities."""

    DEFAULT_CSS = """
    ArbPanel {
        height: auto;
        max-height: 30%;
        min-height: 5;
        border-top: thick #ffcc00;
        padding: 0 1;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #ffcc00]  ARBITRAGE[/]  [dim]guaranteed profit opportunities[/dim]",
            id="arb-header",
        )
        yield Static("[dim]Scanning for arbs...[/dim]", id="arb-content")

    def update_arbs(self, arbs: list[ArbBet]) -> None:
        try:
            content = self.query_one("#arb-content", Static)
        except Exception:
            return

        if not arbs:
            content.update("[dim]  No arbitrage opportunities detected[/dim]")
            return

        content.update(_build_arb_display(arbs))

    def toggle(self) -> None:
        self.display = not self.display
