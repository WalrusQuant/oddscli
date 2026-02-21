"""Player props table: per-book odds display with market filter."""

from __future__ import annotations

from itertools import groupby

from rich.console import Group
from rich.rule import Rule
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Input, Static

from app.api.models import PropRow
from app.services.ev import compute_inline_ev
from app.ui.widgets.constants import BOOK_SHORT, MAX_DISPLAY_BOOKS, PROP_LABELS, trunc


def _bk(key: str) -> str:
    return BOOK_SHORT.get(key, key[:6].upper())


def _odds(price: float) -> str:
    return f"+{int(round(price))}" if price >= 0 else str(int(round(price)))


def _prop_label(market_key: str) -> str:
    return PROP_LABELS.get(market_key, market_key[:6])


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


def _best_with_book(odds_dict: dict[str, float]) -> tuple[float | None, str | None]:
    """Get best price and which book it's from."""
    if not odds_dict:
        return None, None
    best_book = max(odds_dict, key=odds_dict.get)  # type: ignore[arg-type]
    return odds_dict[best_book], best_book


def _is_dfs(book_key: str, dfs_books: dict[str, float] | None) -> bool:
    return bool(dfs_books and book_key in dfs_books)


# ── Display builders ──


def _build_filter_bar(
    active_filter: str, filter_keys: list[str],
    dfs_active: bool = False,
) -> Text:
    """Build the prop market filter toggle bar."""
    bar = Text()
    for fk in filter_keys:
        if fk == active_filter:
            bar.append(f" {fk} ", style="bold white on #333333")
        else:
            bar.append(f" {fk} ", style="dim")
        bar.append(" ")
    bar.append("(t to filter)", style="dim italic")
    if dfs_active:
        bar.append("    ", style="dim")
        bar.append("* = DFS override", style="dim magenta")
    return bar


def _build_header(display_books: list[str]) -> Text:
    h = Text()
    h.append("PLAYER".ljust(20), style="bold #e94560")
    h.append(" ")
    h.append("PROP".center(6), style="bold #e94560")
    h.append(" ")
    h.append("LINE".center(6), style="bold #e94560")
    h.append(" ")
    h.append("NOVIG".center(7), style="bold #e94560")
    h.append("EV%".center(6), style="bold #e94560")
    h.append("BEST".center(10), style="bold #00ff88")
    for bk in display_books:
        h.append(_bk(bk).center(8), style="bold #888888")
    return h


def _build_game_separator(away: str, home: str, commence_time=None) -> Text:
    label = f"  {away} @ {home}"
    if commence_time:
        local_time = commence_time.astimezone()
        label += f"  {local_time.strftime('%-I:%M%p')}"
    label += "  "
    t = Text()
    t.append(label, style="bold yellow on #1a1a2e")
    return t


def _build_prop_pair(
    row: PropRow, display_books: list[str],
    dfs_books: dict[str, float] | None = None,
) -> list[Text]:
    """Build two lines (Over + Under) for a paired PropRow."""
    over_prices = list(row.over_odds.values())
    under_prices = list(row.under_odds.values())

    # Compute inline EV for Over side
    ov_novig, ov_ev = compute_inline_ev(over_prices, under_prices)
    # Compute inline EV for Under side
    un_novig, un_ev = compute_inline_ev(under_prices, over_prices)

    ov_best, ov_best_bk = _best_with_book(row.over_odds)
    un_best, un_best_bk = _best_with_book(row.under_odds)

    # ── Over line ──
    over_line = Text()
    over_line.append(trunc(row.player_name, 20), style="bold white")
    over_line.append(" ")
    over_line.append(_prop_label(row.market_key).center(6), style="magenta")
    over_line.append(" ")
    if row.consensus_point is not None:
        over_line.append(f"O {row.consensus_point:g}".center(6), style="cyan bold")
    else:
        over_line.append("-".center(6), style="dim")
    over_line.append(" ")
    # NOVIG
    if ov_novig is not None:
        over_line.append(_odds(ov_novig).center(7), style="white")
    else:
        over_line.append("-".center(7), style="dim")
    # EV%
    if ov_ev is not None:
        ev_style = "bold #00ff88" if ov_ev > 0 else "dim"
        over_line.append(f"{ov_ev:+.1f}%".center(6), style=ev_style)
    else:
        over_line.append("-".center(6), style="dim")
    # BEST (with book label)
    if ov_best is not None and ov_best_bk:
        label = f"{_odds(ov_best)}/{_short_book(ov_best_bk)}"
        over_line.append(label.center(10), style="bold #00ff88")
    else:
        over_line.append("-".center(10), style="dim")
    # Per-book
    for bk in display_books:
        price = row.over_odds.get(bk)
        is_dfs_bk = _is_dfs(bk, dfs_books)
        if price is not None:
            is_best = ov_best is not None and price >= ov_best
            text = _odds(price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "cyan")
            over_line.append(text.center(8), style=style)
        else:
            over_line.append("-".center(8), style="#555555")

    # ── Under line ──
    under_line = Text()
    under_line.append(" " * 20)  # blank player name
    under_line.append(" ")
    under_line.append(" " * 6)   # blank prop
    under_line.append(" ")
    if row.consensus_point is not None:
        under_line.append(f"U {row.consensus_point:g}".center(6), style="#ff8866 bold")
    else:
        under_line.append("-".center(6), style="dim")
    under_line.append(" ")
    # NOVIG
    if un_novig is not None:
        under_line.append(_odds(un_novig).center(7), style="white")
    else:
        under_line.append("-".center(7), style="dim")
    # EV%
    if un_ev is not None:
        ev_style = "bold #00ff88" if un_ev > 0 else "dim"
        under_line.append(f"{un_ev:+.1f}%".center(6), style=ev_style)
    else:
        under_line.append("-".center(6), style="dim")
    # BEST (with book label)
    if un_best is not None and un_best_bk:
        label = f"{_odds(un_best)}/{_short_book(un_best_bk)}"
        under_line.append(label.center(10), style="bold #00ff88")
    else:
        under_line.append("-".center(10), style="dim")
    # Per-book
    for bk in display_books:
        price = row.under_odds.get(bk)
        is_dfs_bk = _is_dfs(bk, dfs_books)
        if price is not None:
            is_best = un_best is not None and price >= un_best
            text = _odds(price) + ("*" if is_dfs_bk else "")
            style = "bold magenta" if is_dfs_bk else ("bold #00ff88" if is_best else "#ff8866")
            under_line.append(text.center(8), style=style)
        else:
            under_line.append("-".center(8), style="#555555")

    return [over_line, under_line]


def _build_sticky_header(
    active_filter: str, filter_keys: list[str], display_books: list[str],
    dfs_active: bool = False,
) -> Group:
    """Build the sticky portion: filter bar + column headers."""
    return Group(
        _build_filter_bar(active_filter, filter_keys, dfs_active),
        Text(""),
        _build_header(display_books),
        Rule(style="#444444"),
    )


def _precompute_ev(rows: list[PropRow]) -> dict[int, float]:
    """Pre-compute best EV for each row (by id) to avoid redundant calls."""
    ev_cache: dict[int, float] = {}
    for row in rows:
        over_prices = list(row.over_odds.values())
        under_prices = list(row.under_odds.values())
        _, ov_ev = compute_inline_ev(over_prices, under_prices)
        _, un_ev = compute_inline_ev(under_prices, over_prices)
        ev_cache[id(row)] = max(ov_ev or -999, un_ev or -999)
    return ev_cache


def _build_rows(
    rows: list[PropRow],
    active_filter: str,
    display_books: list[str],
    dfs_books: dict[str, float] | None = None,
) -> Group:
    """Build the scrollable prop rows."""
    if active_filter != "ALL":
        rows = [r for r in rows if _prop_label(r.market_key) == active_filter]

    if not rows:
        return Group(Text("  No prop lines found", style="dim"))

    # Pre-compute EV once, then sort using cached values
    ev_cache = _precompute_ev(rows)
    rows = sorted(rows, key=lambda r: (
        r.commence_time, r.event_id, -ev_cache.get(id(r), -999), r.player_name,
    ))

    elements: list = []

    def _game_key(r: PropRow) -> str:
        return r.event_id

    for game_id, game_rows_iter in groupby(rows, key=_game_key):
        game_rows = list(game_rows_iter)
        first = game_rows[0]
        elements.append(_build_game_separator(
            first.away_team, first.home_team, first.commence_time,
        ))
        elements.append(Rule(style="#222222"))
        for row in game_rows:
            pair = _build_prop_pair(row, display_books, dfs_books)
            elements.extend(pair)
            elements.append(Rule(style="#1a1a1a"))

    return Group(*elements)


class PropsTable(Vertical):
    """Player-props display with sticky header and scrollable rows."""

    DEFAULT_CSS = """
    PropsTable {
        height: 1fr;
        padding: 0 1;
        display: none;
    }
    PropsTable #props-header {
        height: auto;
    }
    PropsTable #props-search {
        height: 3;
        margin: 0 0;
        display: none;
    }
    PropsTable #props-search.visible {
        display: block;
    }
    PropsTable #props-scroll {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._filter_idx: int = 0
        self._filter_keys: list[str] = ["ALL"]
        self._last_rows: list[PropRow] | None = None
        self._display_books: list[str] = []
        self._dfs_books: dict[str, float] | None = None
        self._search_query: str = ""
        self._loading: bool = False

    def set_display_books(self, books: list[str]) -> None:
        self._display_books = books[:MAX_DISPLAY_BOOKS]

    def set_dfs_books(self, dfs_books: dict[str, float]) -> None:
        """Set DFS book odds overrides."""
        self._dfs_books = dfs_books or None

    def set_loading(self, loading: bool) -> None:
        """Show/hide loading state."""
        self._loading = loading
        if loading and self._last_rows is None:
            try:
                content = self.query_one("#props-content", Static)
                content.update("[dim]Loading...[/dim]")
            except Exception:
                pass

    def set_sport(self, sport_key: str, props_markets: list[str]) -> None:
        """Update filter keys for the current sport's prop markets."""
        seen: set[str] = set()
        labels: list[str] = []
        for m in props_markets:
            lbl = PROP_LABELS.get(m)
            if lbl and lbl not in seen:
                labels.append(lbl)
                seen.add(lbl)
        self._filter_keys = ["ALL"] + labels
        self._filter_idx = 0

    def cycle_filter(self) -> None:
        """Cycle through prop market filters."""
        self._filter_idx = (self._filter_idx + 1) % len(self._filter_keys)
        if self._last_rows is not None:
            self.update_props(self._last_rows)

    def toggle_search(self) -> None:
        """Show/hide the player search input."""
        try:
            search = self.query_one("#props-search", Input)
        except Exception:
            return
        if search.has_class("visible"):
            search.remove_class("visible")
            self._search_query = ""
            if self._last_rows is not None:
                self.update_props(self._last_rows)
        else:
            search.add_class("visible")
            search.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter props by player name as user types."""
        self._search_query = event.value.strip().lower()
        if self._last_rows is not None:
            self.update_props(self._last_rows)

    def on_key(self, event) -> None:
        """Clear search on Escape."""
        if event.key == "escape":
            try:
                search = self.query_one("#props-search", Input)
                if search.has_class("visible"):
                    search.value = ""
                    search.remove_class("visible")
                    self._search_query = ""
                    if self._last_rows is not None:
                        self.update_props(self._last_rows)
                    event.prevent_default()
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        yield Static(" ", id="props-header")
        yield Input(placeholder="Search player...", id="props-search")
        with ScrollableContainer(id="props-scroll"):
            yield Static("[dim]Waiting for prop data...[/dim]", id="props-content")

    def update_props(self, rows: list[PropRow]) -> None:
        self._last_rows = rows
        self._loading = False
        try:
            header = self.query_one("#props-header", Static)
            content = self.query_one("#props-content", Static)
            scroll = self.query_one("#props-scroll", ScrollableContainer)
        except Exception:
            return

        # Save scroll position
        saved_y = scroll.scroll_y

        dfs_active = bool(self._dfs_books)
        active_filter = self._filter_keys[self._filter_idx]
        header.update(_build_sticky_header(
            active_filter, self._filter_keys, self._display_books, dfs_active,
        ))

        # Apply search filter
        display_rows = rows
        if self._search_query:
            display_rows = [
                r for r in display_rows
                if self._search_query in r.player_name.lower()
            ]

        if not display_rows:
            content.update("[dim]No prop lines found for this sport[/dim]")
            return

        content.update(_build_rows(
            display_rows, active_filter, self._display_books, self._dfs_books,
        ))

        # Restore scroll position
        scroll.call_after_refresh(scroll.scroll_to, y=saved_y, animate=False)
