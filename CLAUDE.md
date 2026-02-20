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

No test suite or linter is currently configured.

## Architecture

Three-layer async app: **API → Services → UI** (Textual 8.0 TUI).

### API Layer (`app/api/`)
- `client.py` — Async httpx wrapper; injects API key, parses credit headers
- `endpoints.py` — Typed fetch functions: `get_sports()`, `get_odds()`, `get_scores()`, `get_events()`
- `models.py` — Pydantic v2 models: `Sport`, `Event`, `Score`, `GameRow`, `Bookmaker`, `Market`, `OutcomeOdds`, `EVBet`

### Services Layer (`app/services/`)
- `data_service.py` — Central orchestrator; coordinates API calls, caching, budget, and EV detection. Merges scores + odds into `GameRow` objects
- `ev.py` — EV engine: computes no-vig consensus odds from 3+ books, compares each book's odds to fair price, filters by `ev_threshold`
- `ev_store.py` — SQLite persistence for EV bets (`ev_history.db`); drops/recreates table on init
- `cache.py` — In-memory TTL cache keyed by `"{sport}:{data_type}"`
- `budget.py` — Tracks API credits from response headers; blocks fetches when critical

### UI Layer (`app/ui/`)
- `app.py` — `OddsTickerApp` (Textual App subclass); manages lifecycle, keybindings, auto-refresh timers
- `widgets/sport_tabs.py` — Sport navigation tabs with reactive `active_index`
- `widgets/games_table.py` — Multi-book odds grid; toggles between h2h/spreads/totals markets
- `widgets/ev_panel.py` — +EV opportunities panel (toggle with `e` key)
- `widgets/status_bar.py` — Credits, refresh time, warnings
- `styles.tcss` — Dark theme CSS

### Data Flow
1. User action (keypress or timer) → App handler
2. `run_worker()` calls `DataService` methods asynchronously
3. DataService checks cache/budget → hits API if needed → returns models
4. App updates widgets via `query_one()` calls

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
