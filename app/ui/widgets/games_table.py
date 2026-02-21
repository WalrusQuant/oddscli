"""Games ticker: multi-book odds display with market toggle."""

from __future__ import annotations

from collections import Counter

from rich.console import Group
from rich.rule import Rule
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Static

from app.api.models import Bookmaker, GameRow
from app.services.ev import compute_inline_ev
from app.ui.widgets.constants import BOOK_SHORT, MAX_DISPLAY_BOOKS, trunc

MARKET_LABELS = {"h2h": "MONEYLINE", "spreads": "SPREAD", "totals": "TOTAL"}
ALT_KEYS = {"spreads": "alternate_spreads", "totals": "alternate_totals"}
GAME_FILTERS = ["ALL", "UPCOMING", "LIVE", "FINAL"]


def _bk(key: str) -> str:
    return BOOK_SHORT.get(key, key[:3].upper())


def _odds(price: float) -> str:
    return f"+{int(price)}" if price >= 0 else str(int(price))


def _resolve_price(
    price: float, book_key: str, dfs_books: dict[str, float] | None,
) -> float:
    """Return configured DFS odds or actual book price."""
    if dfs_books and book_key in dfs_books:
        return dfs_books[book_key]
    return price


def _is_dfs(book_key: str, dfs_books: dict[str, float] | None) -> bool:
    """Check if a book has DFS price override."""
    return bool(dfs_books and book_key in dfs_books)


def _market_keys(market_key: str) -> tuple[str, ...]:
    """Return base + alternate market keys to search."""
    alt = ALT_KEYS.get(market_key)
    return (market_key, alt) if alt else (market_key,)


def _get_book_price(
    game: GameRow,
    outcome_name: str,
    market_key: str,
    book_key: str,
    point: float | None = None,
    dfs_books: dict[str, float] | None = None,
) -> float | None:
    """Get a specific book's best price for an outcome (base + alt markets)."""
    best: float | None = None
    keys = _market_keys(market_key)
    for bm in game.bookmakers:
        if bm.key != book_key:
            continue
        for m in bm.markets:
            if m.key not in keys:
                continue
            for o in m.outcomes:
                if o.name != outcome_name:
                    continue
                if market_key in ("spreads", "totals"):
                    if point is not None and o.point == point:
                        p = _resolve_price(o.price, bm.key, dfs_books)
                        if best is None or p > best:
                            best = p
                else:
                    return _resolve_price(o.price, bm.key, dfs_books)
    return best


def _best_price_with_book(
    game: GameRow,
    outcome_name: str,
    market_key: str,
    point: float | None = None,
    dfs_books: dict[str, float] | None = None,
) -> tuple[float | None, str | None]:
    """Get the best price across ALL books and which book has it."""
    best = None
    best_book = None
    keys = _market_keys(market_key)
    for bm in game.bookmakers:
        for m in bm.markets:
            if m.key not in keys:
                continue
            for o in m.outcomes:
                if o.name != outcome_name:
                    continue
                p = _resolve_price(o.price, bm.key, dfs_books)
                if market_key in ("spreads", "totals"):
                    if point is not None and o.point == point:
                        if best is None or p > best:
                            best = p
                            best_book = bm.key
                else:
                    if best is None or p > best:
                        best = p
                        best_book = bm.key
    return best, best_book


def _all_prices(
    game: GameRow,
    outcome_name: str,
    market_key: str,
    point: float | None = None,
    dfs_books: dict[str, float] | None = None,
) -> list[float]:
    """Collect all book prices for an outcome (for no-vig calculation).

    When alt lines are present, includes prices from alternate markets
    at the same point. Uses only the best price per book to avoid
    double-counting.
    """
    keys = _market_keys(market_key)
    # Best price per book at this point
    per_book: dict[str, float] = {}
    for bm in game.bookmakers:
        for m in bm.markets:
            if m.key not in keys:
                continue
            for o in m.outcomes:
                if o.name != outcome_name:
                    continue
                p = _resolve_price(o.price, bm.key, dfs_books)
                if market_key in ("spreads", "totals"):
                    if point is not None and o.point == point:
                        if bm.key not in per_book or p > per_book[bm.key]:
                            per_book[bm.key] = p
                else:
                    if bm.key not in per_book or p > per_book[bm.key]:
                        per_book[bm.key] = p
    return list(per_book.values())


def _discover_alt_spread_lines(
    game: GameRow, team: str, consensus: float | None,
) -> list[float]:
    """Get all unique spread points for a team from alternate markets."""
    pts: set[float] = set()
    for bm in game.bookmakers:
        for m in bm.markets:
            if m.key != "alternate_spreads":
                continue
            for o in m.outcomes:
                if o.name == team and o.point is not None:
                    pts.add(o.point)
    if consensus is not None:
        pts.discard(consensus)
    return sorted(pts)


def _discover_alt_total_lines(
    game: GameRow, consensus: float | None,
) -> list[float]:
    """Get all unique total points from alternate markets."""
    pts: set[float] = set()
    for bm in game.bookmakers:
        for m in bm.markets:
            if m.key != "alternate_totals":
                continue
            for o in m.outcomes:
                if o.name == "Over" and o.point is not None:
                    pts.add(o.point)
    if consensus is not None:
        pts.discard(consensus)
    return sorted(pts)


def _build_alt_spread_row(
    game: GameRow, a_point: float, h_point: float,
    display_books: list[str], dfs_books: dict[str, float] | None,
) -> tuple[Text, Text]:
    """Build a compact alt-line row pair for spreads (no time/team/score)."""
    away_line = Text()
    home_line = Text()

    # Blank time + team + score columns
    away_line.append(" " * 8)
    away_line.append("  ")
    away_line.append(" " * 22)
    away_line.append(" ")
    away_line.append(" " * 4)
    away_line.append(" ")
    home_line.append(" " * 8)
    home_line.append("  ")
    home_line.append(" " * 22)
    home_line.append(" ")
    home_line.append(" " * 4)
    home_line.append(" ")

    a_outcome = game.away_team
    h_outcome = game.home_team
    market_key = "spreads"

    # LINE column
    sign_a = "+" if a_point > 0 else ""
    away_line.append(f"{sign_a}{a_point}".center(7), style="yellow")
    sign_h = "+" if h_point > 0 else ""
    home_line.append(f"{sign_h}{h_point}".center(7), style="yellow")

    # NOVIG + EV%
    a_prices = _all_prices(game, a_outcome, market_key, a_point, dfs_books)
    h_prices = _all_prices(game, h_outcome, market_key, h_point, dfs_books)
    a_novig, a_ev = compute_inline_ev(a_prices, h_prices)
    h_novig, h_ev = compute_inline_ev(h_prices, a_prices)

    if a_novig is not None:
        away_line.append(_odds(a_novig).center(7), style="white")
    else:
        away_line.append("-".center(7), style="dim")
    if h_novig is not None:
        home_line.append(_odds(h_novig).center(7), style="white")
    else:
        home_line.append("-".center(7), style="dim")

    if a_ev is not None:
        away_line.append(f"{a_ev:+.1f}%".center(6), style="bold #00ff88" if a_ev > 0 else "dim")
    else:
        away_line.append("-".center(6), style="dim")
    if h_ev is not None:
        home_line.append(f"{h_ev:+.1f}%".center(6), style="bold #00ff88" if h_ev > 0 else "dim")
    else:
        home_line.append("-".center(6), style="dim")

    # BEST
    a_best, a_best_bk = _best_price_with_book(game, a_outcome, market_key, a_point, dfs_books)
    h_best, h_best_bk = _best_price_with_book(game, h_outcome, market_key, h_point, dfs_books)

    if a_best is not None and a_best_bk:
        away_line.append(f"{_odds(a_best)}/{_short_book(a_best_bk)}".center(10), style="bold #00ff88")
    else:
        away_line.append("-".center(10), style="dim")
    if h_best is not None and h_best_bk:
        home_line.append(f"{_odds(h_best)}/{_short_book(h_best_bk)}".center(10), style="bold #00ff88")
    else:
        home_line.append("-".center(10), style="dim")

    # Book columns
    for bk in display_books:
        a_price = _get_book_price(game, a_outcome, market_key, bk, a_point, dfs_books)
        h_price = _get_book_price(game, h_outcome, market_key, bk, h_point, dfs_books)
        is_dfs_bk = _is_dfs(bk, dfs_books)

        if a_price is not None:
            is_best = a_best is not None and a_price >= a_best
            text = _odds(a_price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            away_line.append(text.center(8), style=style)
        else:
            away_line.append("-".center(8), style="#555555")

        if h_price is not None:
            is_best = h_best is not None and h_price >= h_best
            text = _odds(h_price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            home_line.append(text.center(8), style=style)
        else:
            home_line.append("-".center(8), style="#555555")

    return away_line, home_line


def _build_alt_total_row(
    game: GameRow, total_point: float,
    display_books: list[str], dfs_books: dict[str, float] | None,
) -> tuple[Text, Text]:
    """Build a compact alt-line row pair for totals (no time/team/score)."""
    away_line = Text()
    home_line = Text()

    # Blank time + team + score columns
    away_line.append(" " * 8)
    away_line.append("  ")
    away_line.append(" " * 22)
    away_line.append(" ")
    away_line.append(" " * 4)
    away_line.append(" ")
    home_line.append(" " * 8)
    home_line.append("  ")
    home_line.append(" " * 22)
    home_line.append(" ")
    home_line.append(" " * 4)
    home_line.append(" ")

    market_key = "totals"

    # LINE column
    away_line.append(f"O {total_point}".center(7), style="magenta")
    home_line.append(f"U {total_point}".center(7), style="magenta")

    # NOVIG + EV%
    a_prices = _all_prices(game, "Over", market_key, total_point, dfs_books)
    h_prices = _all_prices(game, "Under", market_key, total_point, dfs_books)
    a_novig, a_ev = compute_inline_ev(a_prices, h_prices)
    h_novig, h_ev = compute_inline_ev(h_prices, a_prices)

    if a_novig is not None:
        away_line.append(_odds(a_novig).center(7), style="white")
    else:
        away_line.append("-".center(7), style="dim")
    if h_novig is not None:
        home_line.append(_odds(h_novig).center(7), style="white")
    else:
        home_line.append("-".center(7), style="dim")

    if a_ev is not None:
        away_line.append(f"{a_ev:+.1f}%".center(6), style="bold #00ff88" if a_ev > 0 else "dim")
    else:
        away_line.append("-".center(6), style="dim")
    if h_ev is not None:
        home_line.append(f"{h_ev:+.1f}%".center(6), style="bold #00ff88" if h_ev > 0 else "dim")
    else:
        home_line.append("-".center(6), style="dim")

    # BEST
    a_best, a_best_bk = _best_price_with_book(game, "Over", market_key, total_point, dfs_books)
    h_best, h_best_bk = _best_price_with_book(game, "Under", market_key, total_point, dfs_books)

    if a_best is not None and a_best_bk:
        away_line.append(f"{_odds(a_best)}/{_short_book(a_best_bk)}".center(10), style="bold #00ff88")
    else:
        away_line.append("-".center(10), style="dim")
    if h_best is not None and h_best_bk:
        home_line.append(f"{_odds(h_best)}/{_short_book(h_best_bk)}".center(10), style="bold #00ff88")
    else:
        home_line.append("-".center(10), style="dim")

    # Book columns
    for bk in display_books:
        a_price = _get_book_price(game, "Over", market_key, bk, total_point, dfs_books)
        h_price = _get_book_price(game, "Under", market_key, bk, total_point, dfs_books)
        is_dfs_bk = _is_dfs(bk, dfs_books)

        if a_price is not None:
            is_best = a_best is not None and a_price >= a_best
            text = _odds(a_price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            away_line.append(text.center(8), style=style)
        else:
            away_line.append("-".center(8), style="#555555")

        if h_price is not None:
            is_best = h_best is not None and h_price >= h_best
            text = _odds(h_price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            home_line.append(text.center(8), style=style)
        else:
            home_line.append("-".center(8), style="#555555")

    return away_line, home_line


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


def _short_book(book_key: str) -> str:
    """Short 2-3 char abbreviation for best-book labels."""
    short_map = {
        "fanduel": "FD", "draftkings": "DK", "betmgm": "MGM",
        "betrivers": "BR", "bovada": "BOV", "williamhill_us": "CZR",
        "fanatics": "FAN", "espnbet": "ESPN", "hardrockbet": "HR",
        "betonlineag": "BOL", "lowvig": "LV", "ballybet": "BAL",
        "prizepicks": "PP", "underdog": "UD", "fliff": "FL",
    }
    return short_map.get(book_key, book_key[:2].upper())


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
    h.append("NOVIG".center(7), style="bold #e94560")
    h.append("EV%".center(6), style="bold #e94560")
    h.append("BEST".center(10), style="bold #00ff88")
    for bk in display_books:
        h.append(_bk(bk).center(8), style="bold #888888")
    return h


def _build_game_lines(
    game: GameRow, market: str, display_books: list[str],
    dfs_books: dict[str, float] | None = None,
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
    away_line.append(trunc(game.away_team, 22), style="bold white")
    home_line.append(trunc(game.home_team, 22), style="white")

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

    # ── NOVIG + EV% columns ──
    a_prices = _all_prices(game, a_outcome, market, a_point, dfs_books)
    h_prices = _all_prices(game, h_outcome, market, h_point, dfs_books)

    a_novig, a_ev = compute_inline_ev(a_prices, h_prices)
    h_novig, h_ev = compute_inline_ev(h_prices, a_prices)

    # NOVIG
    if a_novig is not None:
        away_line.append(_odds(a_novig).center(7), style="white")
    else:
        away_line.append("-".center(7), style="dim")
    if h_novig is not None:
        home_line.append(_odds(h_novig).center(7), style="white")
    else:
        home_line.append("-".center(7), style="dim")

    # EV%
    if a_ev is not None:
        ev_style = "bold #00ff88" if a_ev > 0 else "dim"
        away_line.append(f"{a_ev:+.1f}%".center(6), style=ev_style)
    else:
        away_line.append("-".center(6), style="dim")
    if h_ev is not None:
        ev_style = "bold #00ff88" if h_ev > 0 else "dim"
        home_line.append(f"{h_ev:+.1f}%".center(6), style=ev_style)
    else:
        home_line.append("-".center(6), style="dim")

    # ── BEST column (with book label) ──
    a_best, a_best_bk = _best_price_with_book(game, a_outcome, market, a_point, dfs_books)
    h_best, h_best_bk = _best_price_with_book(game, h_outcome, market, h_point, dfs_books)

    if a_best is not None and a_best_bk:
        label = f"{_odds(a_best)}/{_short_book(a_best_bk)}"
        away_line.append(label.center(10), style="bold #00ff88")
    else:
        away_line.append("-".center(10), style="dim")

    if h_best is not None and h_best_bk:
        label = f"{_odds(h_best)}/{_short_book(h_best_bk)}"
        home_line.append(label.center(10), style="bold #00ff88")
    else:
        home_line.append("-".center(10), style="dim")

    # ── Individual book columns ──
    for bk in display_books:
        a_price = _get_book_price(game, a_outcome, market, bk, a_point, dfs_books)
        h_price = _get_book_price(game, h_outcome, market, bk, h_point, dfs_books)
        is_dfs_bk = _is_dfs(bk, dfs_books)

        if a_price is not None:
            is_best = a_best is not None and a_price >= a_best
            text = _odds(a_price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            away_line.append(text.center(8), style=style)
        else:
            away_line.append("-".center(8), style="#555555")

        if h_price is not None:
            is_best = h_best is not None and h_price >= h_best
            text = _odds(h_price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            home_line.append(text.center(8), style=style)
        else:
            home_line.append("-".center(8), style="#555555")

    return away_line, home_line


def _build_sticky_header(
    market: str, display_books: list[str],
    game_filter: str = "ALL",
    dfs_active: bool = False,
) -> Group:
    """Build the sticky portion: toggle bar + filter bar + column headers."""
    toggle = Text()
    for mkt, label in MARKET_LABELS.items():
        if mkt == market:
            toggle.append(f" {label} ", style="bold white on #333333")
        else:
            toggle.append(f" {label} ", style="dim")
        toggle.append("  ")
    toggle.append("(1/2/3 to switch)", style="dim italic")

    # Filter bar
    filter_bar = Text()
    filter_bar.append("  Filter: ", style="dim")
    for f in GAME_FILTERS:
        if f == game_filter:
            filter_bar.append(f" {f} ", style="bold white on #333333")
        else:
            filter_bar.append(f" {f} ", style="dim")
        filter_bar.append(" ")
    filter_bar.append("(f to cycle)", style="dim italic")
    if dfs_active:
        filter_bar.append("    ", style="dim")
        filter_bar.append("* = DFS override", style="dim magenta")

    return Group(
        toggle, filter_bar, Text(""),
        _build_header(market, display_books),
        Rule(style="#444444"),
    )


def _filter_games(games: list[GameRow], game_filter: str) -> list[GameRow]:
    """Filter games by status."""
    if game_filter == "ALL":
        return games
    elif game_filter == "UPCOMING":
        return [g for g in games if g.home_score == "-" and not g.completed]
    elif game_filter == "LIVE":
        return [g for g in games if g.home_score != "-" and not g.completed]
    elif game_filter == "FINAL":
        return [g for g in games if g.completed]
    return games


def _build_rows(
    games: list[GameRow], market: str, display_books: list[str],
    dfs_books: dict[str, float] | None = None,
    alt_lines: bool = False,
) -> Group:
    """Build the scrollable game rows."""
    if not games:
        return Group(Text("  No games found for this sport", style="dim"))

    elements: list = []
    for i, game in enumerate(games):
        away_line, home_line = _build_game_lines(
            game, market, display_books, dfs_books,
        )
        elements.extend([away_line, home_line])

        # Expand alt lines below the consensus row
        if alt_lines and market == "spreads":
            cons_a = _consensus_spread(game.bookmakers, game.away_team)
            alt_pts = _discover_alt_spread_lines(game, game.away_team, cons_a)
            for apt in alt_pts:
                hpt = -apt  # opposite side
                a_row, h_row = _build_alt_spread_row(
                    game, apt, hpt, display_books, dfs_books,
                )
                elements.extend([a_row, h_row])

        elif alt_lines and market == "totals":
            cons_t = _consensus_total(game.bookmakers)
            alt_pts = _discover_alt_total_lines(game, cons_t)
            for tpt in alt_pts:
                a_row, h_row = _build_alt_total_row(
                    game, tpt, display_books, dfs_books,
                )
                elements.extend([a_row, h_row])

        if i < len(games) - 1:
            elements.append(Rule(style="#222222"))

    return Group(*elements)


class GamesTicker(Vertical):
    """Multi-book odds display with sticky header and scrollable rows."""

    DEFAULT_CSS = """
    GamesTicker {
        height: 1fr;
        padding: 0 1;
    }
    GamesTicker #games-header {
        height: auto;
    }
    GamesTicker #games-scroll {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._market: str = "h2h"
        self._last_games: list[GameRow] | None = None
        self._display_books: list[str] = []
        self._dfs_books: dict[str, float] | None = None
        self._game_filter: str = "ALL"
        self._loading: bool = False
        self._alt_lines: bool = False

    def set_alt_lines(self, enabled: bool) -> None:
        """Toggle alternate line display."""
        self._alt_lines = enabled

    def set_display_books(self, books: list[str]) -> None:
        """Set which bookmakers to display as columns."""
        self._display_books = books[:MAX_DISPLAY_BOOKS]

    def set_dfs_books(self, dfs_books: dict[str, float]) -> None:
        """Set DFS book odds overrides."""
        self._dfs_books = dfs_books or None

    def set_loading(self, loading: bool) -> None:
        """Show/hide loading state."""
        self._loading = loading
        if loading and self._last_games is None:
            try:
                content = self.query_one("#games-content", Static)
                content.update("[dim]Loading...[/dim]")
            except Exception:
                pass

    def toggle_market(self) -> None:
        """Cycle through h2h -> spreads -> totals."""
        markets = ["h2h", "spreads", "totals"]
        idx = markets.index(self._market)
        self._market = markets[(idx + 1) % len(markets)]
        if self._last_games is not None:
            self.update_games(self._last_games)

    def set_market(self, market: str) -> None:
        """Set market directly (1=h2h, 2=spreads, 3=totals)."""
        if market in MARKET_LABELS and market != self._market:
            self._market = market
            if self._last_games is not None:
                self.update_games(self._last_games)

    def cycle_filter(self) -> None:
        """Cycle through game status filters."""
        idx = GAME_FILTERS.index(self._game_filter)
        self._game_filter = GAME_FILTERS[(idx + 1) % len(GAME_FILTERS)]
        if self._last_games is not None:
            self.update_games(self._last_games)

    def compose(self) -> ComposeResult:
        yield Static(" ", id="games-header")
        with ScrollableContainer(id="games-scroll"):
            yield Static("[dim]Waiting for data...[/dim]", id="games-content")

    def update_games(self, games: list[GameRow]) -> None:
        self._last_games = games
        self._loading = False
        try:
            header = self.query_one("#games-header", Static)
            content = self.query_one("#games-content", Static)
            scroll = self.query_one("#games-scroll", ScrollableContainer)
        except Exception:
            return

        # Save scroll position
        saved_y = scroll.scroll_y

        dfs_active = bool(self._dfs_books)
        header.update(_build_sticky_header(
            self._market, self._display_books, self._game_filter, dfs_active,
        ))

        filtered = _filter_games(games, self._game_filter)
        if not filtered:
            content.update("[dim]No games found for this sport[/dim]")
            return

        content.update(_build_rows(
            filtered, self._market, self._display_books, self._dfs_books,
            alt_lines=self._alt_lines,
        ))

        # Restore scroll position
        scroll.call_after_refresh(scroll.scroll_to, y=saved_y, animate=False)
