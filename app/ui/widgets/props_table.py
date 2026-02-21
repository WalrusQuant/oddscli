"""Player props table: per-book odds display with market filter."""

from __future__ import annotations

from itertools import groupby

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from app.api.models import PropRow
from app.services.ev import compute_inline_ev
from app.ui.widgets.constants import BOOK_SHORT, MAX_DISPLAY_BOOKS, PROP_LABELS


def _bk(key: str) -> str:
    return BOOK_SHORT.get(key, key[:6].upper())


def _odds(price: float) -> str:
    return f"+{int(price)}" if price >= 0 else str(int(price))


def _prop_label(market_key: str) -> str:
    return PROP_LABELS.get(market_key, market_key[:6])


# ── Display builders ──


def _build_filter_bar(active_filter: str, filter_keys: list[str]) -> Text:
    """Build the prop market filter toggle bar."""
    bar = Text()
    for fk in filter_keys:
        if fk == active_filter:
            bar.append(f" {fk} ", style="bold white on #333333")
        else:
            bar.append(f" {fk} ", style="dim")
        bar.append(" ")
    bar.append("(m to filter)", style="dim italic")
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
    h.append("BEST".center(8), style="bold #00ff88")
    for bk in display_books:
        h.append(_bk(bk).center(8), style="bold #888888")
    return h


def _build_game_separator(away: str, home: str) -> Text:
    label = f"  {away} @ {home}  "
    t = Text()
    t.append(label, style="bold yellow on #1a1a2e")
    return t


def _build_prop_pair(row: PropRow, display_books: list[str]) -> list[Text]:
    """Build two lines (Over + Under) for a paired PropRow."""
    over_prices = list(row.over_odds.values())
    under_prices = list(row.under_odds.values())

    # Compute inline EV for Over side
    ov_novig, ov_ev = compute_inline_ev(over_prices, under_prices)
    # Compute inline EV for Under side
    un_novig, un_ev = compute_inline_ev(under_prices, over_prices)

    ov_best = max(over_prices) if over_prices else None
    un_best = max(under_prices) if under_prices else None

    # ── Over line ──
    over_line = Text()
    over_line.append(row.player_name[:20].ljust(20), style="bold white")
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
    # BEST
    if ov_best is not None:
        over_line.append(_odds(ov_best).center(8), style="bold #00ff88")
    else:
        over_line.append("-".center(8), style="dim")
    # Per-book
    for bk in display_books:
        price = row.over_odds.get(bk)
        if price is not None:
            is_best = ov_best is not None and price >= ov_best
            over_line.append(
                _odds(price).center(8),
                style="bold #00ff88" if is_best else "cyan",
            )
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
    # BEST
    if un_best is not None:
        under_line.append(_odds(un_best).center(8), style="bold #00ff88")
    else:
        under_line.append("-".center(8), style="dim")
    # Per-book
    for bk in display_books:
        price = row.under_odds.get(bk)
        if price is not None:
            is_best = un_best is not None and price >= un_best
            under_line.append(
                _odds(price).center(8),
                style="bold #00ff88" if is_best else "#ff8866",
            )
        else:
            under_line.append("-".center(8), style="#555555")

    return [over_line, under_line]


def _build_sticky_header(
    active_filter: str, filter_keys: list[str], display_books: list[str],
) -> Group:
    """Build the sticky portion: filter bar + column headers."""
    return Group(
        _build_filter_bar(active_filter, filter_keys),
        Text(""),
        _build_header(display_books),
        Rule(style="#444444"),
    )


def _build_rows(
    rows: list[PropRow],
    active_filter: str,
    display_books: list[str],
) -> Group:
    """Build the scrollable prop rows."""
    if active_filter != "ALL":
        rows = [r for r in rows if _prop_label(r.market_key) == active_filter]

    if not rows:
        return Group(Text("  No prop lines found", style="dim"))

    elements: list = []

    def _game_key(r: PropRow) -> str:
        return r.event_id

    for game_id, game_rows_iter in groupby(rows, key=_game_key):
        game_rows = list(game_rows_iter)
        first = game_rows[0]
        elements.append(_build_game_separator(first.away_team, first.home_team))
        elements.append(Rule(style="#222222"))
        for row in game_rows:
            pair = _build_prop_pair(row, display_books)
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

    def set_display_books(self, books: list[str]) -> None:
        self._display_books = books[:MAX_DISPLAY_BOOKS]

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

    def compose(self) -> ComposeResult:
        yield Static(" ", id="props-header")
        with VerticalScroll(id="props-scroll"):
            yield Static("[dim]Waiting for prop data...[/dim]", id="props-content")

    def update_props(self, rows: list[PropRow]) -> None:
        self._last_rows = rows
        try:
            header = self.query_one("#props-header", Static)
            content = self.query_one("#props-content", Static)
        except Exception:
            return

        active_filter = self._filter_keys[self._filter_idx]
        header.update(_build_sticky_header(
            active_filter, self._filter_keys, self._display_books,
        ))

        if not rows:
            content.update("[dim]No prop lines found for this sport[/dim]")
            return

        content.update(_build_rows(rows, active_filter, self._display_books))
