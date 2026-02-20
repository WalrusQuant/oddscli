"""Games ticker: multi-book odds display with market toggle."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from app.api.models import Bookmaker, GameRow

BOOK_SHORT: dict[str, str] = {
    "fanduel": "FanDuel", "draftkings": "DraftK", "betmgm": "BetMGM",
    "betrivers": "BetRiv", "betonlineag": "BetOnl", "betus": "BetUS",
    "bovada": "Bovada", "williamhill_us": "Caesars", "fanatics": "Fanatic",
    "lowvig": "LowVig", "mybookieag": "MyBook", "ballybet": "Bally",
    "betanysports": "BetAny", "betparx": "BetPrx", "espnbet": "ESPN",
    "fliff": "Fliff", "hardrockbet": "HrdRck", "rebet": "Rebet",
    "betopenly": "BetOpn", "kalshi": "Kalshi", "novig": "Novig",
    "polymarket": "PolyMk", "prophetx": "PrphX",
}

MARKET_LABELS = {"h2h": "MONEYLINE", "spreads": "SPREAD", "totals": "TOTAL"}
MAX_DISPLAY_BOOKS = 20


def _bk(key: str) -> str:
    return BOOK_SHORT.get(key, key[:3].upper())


def _odds(price: float) -> str:
    return f"+{int(price)}" if price >= 0 else str(int(price))


def _get_book_price(
    game: GameRow,
    outcome_name: str,
    market_key: str,
    book_key: str,
    point: float | None = None,
) -> float | None:
    """Get a specific book's price for an outcome."""
    for bm in game.bookmakers:
        if bm.key != book_key:
            continue
        for m in bm.markets:
            if m.key != market_key:
                continue
            for o in m.outcomes:
                if o.name != outcome_name:
                    continue
                if market_key in ("spreads", "totals"):
                    if point is not None and o.point == point:
                        return o.price
                else:
                    return o.price
    return None


def _best_price(
    game: GameRow,
    outcome_name: str,
    market_key: str,
    point: float | None = None,
) -> float | None:
    """Get the best price across ALL books for an outcome."""
    best = None
    for bm in game.bookmakers:
        for m in bm.markets:
            if m.key != market_key:
                continue
            for o in m.outcomes:
                if o.name != outcome_name:
                    continue
                if market_key in ("spreads", "totals"):
                    if point is not None and o.point == point:
                        if best is None or o.price > best:
                            best = o.price
                else:
                    if best is None or o.price > best:
                        best = o.price
    return best


def _consensus_spread(bookmakers: list[Bookmaker], team: str) -> float | None:
    """Get the consensus spread point for a team."""
    pts: list[float] = []
    for bm in bookmakers:
        for m in bm.markets:
            if m.key != "spreads":
                continue
            for o in m.outcomes:
                if o.name == team and o.point is not None:
                    pts.append(o.point)
    if not pts:
        return None
    return Counter(pts).most_common(1)[0][0]


def _consensus_total(bookmakers: list[Bookmaker]) -> float | None:
    """Get the consensus total line."""
    pts: list[float] = []
    for bm in bookmakers:
        for m in bm.markets:
            if m.key != "totals":
                continue
            for o in m.outcomes:
                if o.name == "Over" and o.point is not None:
                    pts.append(o.point)
    if not pts:
        return None
    return Counter(pts).most_common(1)[0][0]


# ── Display builders ──


def _build_header(market: str, display_books: list[str]) -> Text:
    """Build column header for the current market."""
    h = Text()
    h.append(" " * 8)                                       # time
    h.append("  ")
    h.append("TEAM".ljust(22), style="bold #e94560")
    h.append(" ")
    h.append("SC".center(4), style="bold #e94560")
    h.append(" ")
    if market in ("spreads", "totals"):
        h.append("LINE".center(7), style="bold #e94560")
    h.append("BEST".center(8), style="bold #00ff88")
    for bk in display_books:
        h.append(_bk(bk).center(8), style="bold #888888")
    return h


def _build_game_lines(
    game: GameRow, market: str, display_books: list[str],
) -> tuple[Text, Text]:
    """Build away + home lines for one game."""
    away_line = Text()
    home_line = Text()

    # ── Time / Status ──
    if game.completed:
        away_line.append("FINAL".rjust(8), style="red")
    elif game.home_score != "-":
        away_line.append("LIVE".rjust(8), style="green")
    else:
        local_time = game.commence_time.astimezone()
        away_line.append(
            local_time.strftime("%-I:%M%p").rjust(8), style="dim"
        )
    home_line.append(" " * 8)

    away_line.append("  ")
    home_line.append("  ")

    # ── Teams ──
    away_line.append(game.away_team[:22].ljust(22), style="bold white")
    home_line.append(game.home_team[:22].ljust(22), style="white")

    away_line.append(" ")
    home_line.append(" ")

    # ── Score ──
    a_sc, h_sc = game.away_score, game.home_score
    if a_sc != "-" and h_sc != "-":
        a_lead = a_sc.isdigit() and h_sc.isdigit() and int(a_sc) > int(h_sc)
        h_lead = a_sc.isdigit() and h_sc.isdigit() and int(h_sc) > int(a_sc)
        away_line.append(
            a_sc.center(4),
            style="bold white" if a_lead else ("dim" if h_lead else ""),
        )
        home_line.append(
            h_sc.center(4),
            style="bold white" if h_lead else ("dim" if a_lead else ""),
        )
    else:
        away_line.append(" " * 4)
        home_line.append(" " * 4)

    away_line.append(" ")
    home_line.append(" ")

    # ── Determine outcome names and consensus points ──
    if market == "h2h":
        a_outcome = game.away_team
        h_outcome = game.home_team
        a_point: float | None = None
        h_point: float | None = None
    elif market == "spreads":
        a_outcome = game.away_team
        h_outcome = game.home_team
        a_point = _consensus_spread(game.bookmakers, game.away_team)
        h_point = _consensus_spread(game.bookmakers, game.home_team)
    else:  # totals
        a_outcome = "Over"
        h_outcome = "Under"
        ct = _consensus_total(game.bookmakers)
        a_point = ct
        h_point = ct

    # ── LINE column (spreads/totals only) ──
    if market == "spreads":
        if a_point is not None:
            sign = "+" if a_point > 0 else ""
            away_line.append(f"{sign}{a_point}".center(7), style="yellow bold")
        else:
            away_line.append("-".center(7), style="dim")
        if h_point is not None:
            sign = "+" if h_point > 0 else ""
            home_line.append(f"{sign}{h_point}".center(7), style="yellow bold")
        else:
            home_line.append("-".center(7), style="dim")
    elif market == "totals":
        if a_point is not None:
            away_line.append(f"O {a_point}".center(7), style="magenta bold")
            home_line.append(f"U {a_point}".center(7), style="magenta bold")
        else:
            away_line.append("-".center(7), style="dim")
            home_line.append("-".center(7), style="dim")

    # ── BEST column ──
    a_best = _best_price(game, a_outcome, market, a_point)
    h_best = _best_price(game, h_outcome, market, h_point)

    if a_best is not None:
        away_line.append(_odds(a_best).center(8), style="bold #00ff88")
    else:
        away_line.append("-".center(8), style="dim")

    if h_best is not None:
        home_line.append(_odds(h_best).center(8), style="bold #00ff88")
    else:
        home_line.append("-".center(8), style="dim")

    # ── Individual book columns ──
    for bk in display_books:
        a_price = _get_book_price(game, a_outcome, market, bk, a_point)
        h_price = _get_book_price(game, h_outcome, market, bk, h_point)

        if a_price is not None:
            is_best = a_best is not None and a_price >= a_best
            away_line.append(
                _odds(a_price).center(8),
                style="bold #00ff88" if is_best else "cyan",
            )
        else:
            away_line.append("-".center(8), style="#555555")

        if h_price is not None:
            is_best = h_best is not None and h_price >= h_best
            home_line.append(
                _odds(h_price).center(8),
                style="bold #00ff88" if is_best else "cyan",
            )
        else:
            home_line.append("-".center(8), style="#555555")

    return away_line, home_line


def _build_display(
    games: list[GameRow], market: str, display_books: list[str],
) -> Group:
    """Build the full games display."""
    # Market toggle bar
    toggle = Text()
    for mkt, label in MARKET_LABELS.items():
        if mkt == market:
            toggle.append(f" {label} ", style="bold white on #333333")
        else:
            toggle.append(f" {label} ", style="dim")
        toggle.append("  ")
    toggle.append("(m to toggle)", style="dim italic")

    elements: list = [
        toggle,
        Text(""),
        _build_header(market, display_books),
        Rule(style="#444444"),
    ]

    for i, game in enumerate(games):
        away_line, home_line = _build_game_lines(game, market, display_books)
        elements.extend([away_line, home_line])
        if i < len(games) - 1:
            elements.append(Rule(style="#222222"))

    return Group(*elements)


class GamesTicker(VerticalScroll):
    """Scrollable multi-book odds display with market toggle."""

    DEFAULT_CSS = """
    GamesTicker {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._market: str = "h2h"
        self._last_games: list[GameRow] | None = None
        self._display_books: list[str] = []

    def set_display_books(self, books: list[str]) -> None:
        """Set which bookmakers to display as columns."""
        self._display_books = books[:MAX_DISPLAY_BOOKS]

    def toggle_market(self) -> None:
        """Cycle through h2h → spreads → totals."""
        markets = ["h2h", "spreads", "totals"]
        idx = markets.index(self._market)
        self._market = markets[(idx + 1) % len(markets)]
        if self._last_games is not None:
            self.update_games(self._last_games)

    def compose(self) -> ComposeResult:
        yield Static("[dim]Waiting for data...[/dim]", id="games-content")

    def update_games(self, games: list[GameRow]) -> None:
        self._last_games = games
        try:
            content = self.query_one("#games-content", Static)
        except Exception:
            return

        if not games:
            content.update("[dim]No games found for this sport[/dim]")
            return

        content.update(_build_display(games, self._market, self._display_books))
