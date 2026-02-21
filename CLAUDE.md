# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
source .venv/bin/activate
python -m app.main          # or: oddscli (if installed via pip install -e .)
```

Requires `ODDS_API_KEY` in `.env` and user prefs in `settings.yaml`.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Tests & Linting

Dev tools are configured in `pyproject.toml` under `[project.optional-dependencies] dev`:

```bash
pip install -e ".[dev]"
pytest tests/                        # run all tests
pytest tests/test_ev.py              # single test file
pytest tests/test_ev.py -k "test_name"  # single test
ruff check app/                      # lint
mypy app/                            # type check
```

pytest uses `asyncio_mode = "auto"`. Ruff targets py312, line-length 100, ignores E501.

## Architecture

Three-layer async app: **API → Services → UI** (Textual 8.0 TUI).

### API Layer (`app/api/`)
- `client.py` — Async httpx wrapper; injects API key, parses credit headers
- `endpoints.py` — Typed fetch functions: `get_sports()`, `get_odds()`, `get_scores()`, `get_events()`, `get_event_odds()`, `get_props_for_events()`
- `models.py` — Pydantic v2 models: `Sport`, `Event`, `Score`, `GameRow`, `Bookmaker`, `Market`, `OutcomeOdds`, `PropRow`

### Services Layer (`app/services/`)
- `data_service.py` — Central orchestrator; coordinates API calls, caching, budget, and EV detection. Merges scores + odds into `GameRow` objects. Fetches props per-event with semaphore-limited concurrency.
- `ev.py` — EV/arb/middles engine. Models: `EVBet`, `ArbBet`, `MiddleBet`. Key functions: `find_ev_bets()`, `find_arb_bets()`, `find_middle_bets()`, and their prop variants (`find_prop_arb_bets()`, `find_prop_middle_bets()`). Computes no-vig consensus odds from 3+ books, compares each book's odds to fair price, filters by `ev_threshold`. Props EV normalizes Over/Under pairs independently per (player, market, line). Arb detection finds two-leg guaranteed-profit opportunities. Middles detection finds cross-line windows with sport-specific hit probability estimation.
- `ev_store.py` — SQLite persistence for EV bets (`ev_history.db`); drops/recreates table on init. Tracks both game and prop EV via `is_prop` flag.
- `cache.py` — In-memory TTL cache keyed by `"{sport}:{data_type}"`
- `budget.py` — Tracks API credits from response headers; blocks fetches when critical

### UI Layer (`app/ui/`)
- `app.py` — `OddsTickerApp` (Textual App subclass); manages lifecycle, keybindings, auto-refresh timers, settings panel rendering
- `widgets/games_table.py` — Multi-book odds grid; toggles between h2h/spreads/totals markets with inline no-vig & EV%
- `widgets/props_table.py` — Player props paired Over/Under display with inline EV, sticky header, sport-aware market filtering
- `widgets/ev_panel.py` — +EV opportunities panel (toggle with `e` key); shows both game and prop EV bets
- `widgets/arb_panel.py` — Arbitrage opportunities panel (toggle with `a` key); shows guaranteed-profit two-leg arbs with bet sizing
- `widgets/middles_panel.py` — Middles (cross-line) opportunities panel (toggle with `m` key); shows EV%, hit probability, and window size
- `widgets/sport_tabs.py` — Sport navigation tabs with reactive `active_index`; posts `SportTabs.Changed` messages
- `widgets/status_bar.py` — Credits, refresh time, warnings, keybinding hints
- `widgets/constants.py` — Shared constants: `BOOK_SHORT` (display abbreviations), `PROP_LABELS` (market key → short label), `MAX_DISPLAY_BOOKS`
- `styles.tcss` — Dark theme CSS

### Data Flow

**Games view:** User action → `_load_data()` → `get_game_rows()` (merge scores + odds) → `get_ev_bets()` / `find_arb_bets()` / `find_middle_bets()` → `ticker.update_games()` + panels update

**Props view:** User action → `_load_props()` → `fetch_props()` (per-event API calls) → `get_prop_rows()` → `get_prop_ev_bets()` / `find_prop_arb_bets()` / `find_prop_middle_bets()` → `props_table.update_props()` + panels update

Workers use `run_worker(exclusive=True, group="load")` to prevent concurrent fetches.

### Keybindings (app.py BINDINGS)
`q` quit, `left/right` switch sport, `1/2/3` moneyline/spread/total, `r` refresh, `p` toggle games/props view, `e` EV panel, `a` arb panel, `m` middles panel, `f` book filter, `t` cycle prop market filter, `/` search props, `l` toggle alt lines, `s` settings panel.

### View Mode Switching
App maintains `_view_mode` ("games" or "props"), toggled with `p`. Switches visibility via CSS `display` + class toggling. Games and props have independent auto-refresh timers (`_odds_timer`, `_scores_timer`, `_props_timer`).

### DFS Books
DFS platforms (PrizePicks, Underdog, etc.) get odds overrides from `settings.yaml` `dfs_books` dict. Applied via `_resolve_price()` in games_table and `_effective_price()` in ev.py — replaces API odds with the configured effective juice.

### Config Loading (`app/config.py`)
`load_settings()` merges `.env` (API key via dotenv) + `settings.yaml` (prefs via PyYAML) into a Pydantic `Settings` model.

## Textual 8.0 Gotchas

- **Never name a method `_render()` on a Widget** — shadows Textual's internal method. Use `_refresh_content()` or similar.
- **Never initialize `Static("")`** — causes `visual = None` render errors. Use non-empty content.
- **Never `await` long async ops in `on_mount()`** — blocks the message loop. Use `run_worker()` instead.
- **Never name a guard flag `_ready`** — shadows Textual's internal `_ready()`. The app uses `_init_done`.
- **Avoid em-dash "—" in `.center(N)` columns** — it's double-width in terminals. Use ASCII dash "-".

## Key Conventions

- Python 3.12, type hints throughout (using `X | Y` union syntax)
- All I/O is async (httpx, SQLite via sync in workers, Textual timers)
- Reactive properties on widgets drive state → watchers post messages → App handlers respond
- EV reference: market-average no-vig consensus pricing (not pinned to any single book)
- Inline EV (`compute_inline_ev()`) displayed on-the-fly in tables; persistent EV stored in SQLite for history
- Props require per-event API calls (not bulk), so they cost more credits and refresh less frequently
