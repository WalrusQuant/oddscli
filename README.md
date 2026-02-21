# OddsCLI

A terminal-based sports odds ticker that pulls real-time lines from 20+ bookmakers and surfaces +EV betting opportunities.

Built with Python, [Textual](https://textual.textualize.io/), and [The Odds API](https://the-odds-api.com/).

![Odds Table](assets/odds-table.png)

## Features

- **Live odds from 20+ US bookmakers** — FanDuel, DraftKings, BetMGM, ESPN Bet, and more
- **Three markets** — Toggle between moneyline, spreads, and totals
- **Player props** — Browse player prop lines across books with sport-specific markets (PTS, REB, AST, Pass Yds, HR, etc.)
- **DFS book support** — PrizePicks, Underdog, Pick6, and Betr with configurable effective odds for multi-leg pricing
- **Inline no-vig & EV%** — Fair odds and expected value shown directly in both game and prop tables
- **Best price highlighting** — Instantly see the best available odds across all books
- **+EV detection** — Finds +EV game bets and player props using no-vig consensus pricing
- **Sticky headers** — Column headers stay visible while scrolling through large tables
- **Live scores** — Game status, scores, and start times
- **API credit management** — Tracks usage and gracefully degrades when credits run low
- **Configurable** — Choose your sports, bookmakers, refresh intervals, and EV threshold

## Installation

**Prerequisites:** Python 3.11+ and an API key from [The Odds API](https://the-odds-api.com/) (free tier available)

```bash
git clone https://github.com/WalrusQuant/oddsapi.git
cd oddsapi
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy the example env file and add your API key:

```bash
cp .env.example .env
```

```
ODDS_API_KEY=your_api_key_here
```

## Usage

```bash
oddscli
```

Or run directly:

```bash
python -m app.main
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `Left` / `Right` | Switch sport |
| `r` | Force refresh |
| `m` | Cycle market (moneyline / spread / total in games; filter props by market in props view) |
| `p` | Toggle between games and player props views |
| `e` | Toggle EV panel |
| `s` | Toggle settings panel |

## Player Props

Press `p` to switch to the player props view. Props are fetched concurrently across all events for the selected sport and displayed with:

- **Player name**, prop type, and Over/Under lines from each book
- **NOVIG** column — fair no-vig odds derived from the market consensus
- **EV%** column — inline expected value of the best available price
- **Best price** highlighted across all books

Use `m` to filter by specific prop markets. Available markets vary by sport:

| Sport | Markets |
|-------|---------|
| NBA | PTS, REB, AST, 3PT, PRA |
| NFL | PaYd, PaTD, RuYd, ReYd, Rec, ATD |
| MLB | HR, Hits, TB, K |
| NHL | Goal, SOG, Asst |

### DFS Books

DFS platforms (PrizePicks, Underdog, Pick6, Betr) are supported with configurable effective odds to account for multi-leg pricing differences. Set overrides in `settings.yaml`:

```yaml
dfs_books:
  prizepicks: -137
  underdog: -137
  pick6: -137
  betr_us_dfs: -137
```

## +EV Detection

Toggle the EV panel with `e` to see bets where a bookmaker's odds exceed the fair market price. The panel shows +EV opportunities for both game lines and player props.

![EV Panel](assets/ev-panel.png)

The engine uses **market-average no-vig consensus pricing** to estimate fair odds:

1. Collects odds from all available bookmakers for each outcome
2. Converts to implied probabilities and averages across books
3. Removes the vig (normalizes probabilities to sum to 1.0)
4. Compares each book's actual odds against the derived fair odds
5. Flags bets where EV% exceeds the configured threshold (default 2%)

For player props, Over/Under pairs are normalized independently per (player, market, line) to prevent inflated EV calculations.

Requires at least 3 books contributing to the market average for reliability. Only pre-game lines are evaluated.

## Configuration

Press `s` to view your current settings, or edit `settings.yaml` directly:

![Settings Panel](assets/settings-panel.png)

| Setting | Default | Description |
|---------|---------|-------------|
| `sports` | NFL, NBA, MLB, NHL, NCAAB | Which sports to display |
| `bookmakers` | 20+ US books | Books to compare odds across |
| `regions` | us, us2, us_ex | API regions to pull from |
| `odds_refresh_interval` | 60 | Seconds between odds refreshes |
| `scores_refresh_interval` | 60 | Seconds between score refreshes |
| `ev_threshold` | 2.0 | Minimum EV% to flag a bet |
| `odds_format` | american | `american` or `decimal` |
| `props_refresh_interval` | 300 | Seconds between props refreshes |
| `props_max_concurrent` | 5 | Max concurrent event fetches for props |
| `dfs_books` | {} | DFS book effective odds overrides |
| `props_markets` | per-sport | Player prop markets to fetch per sport |
| `low_credit_warning` | 50 | Show warning at this credit level |
| `critical_credit_stop` | 10 | Pause API calls at this credit level |

## API Credit Usage

The Odds API uses a credit system. The app tracks your remaining credits via response headers and adjusts behavior:

- **Normal** — Fetches odds, scores, and props on configured intervals
- **Low credits** (< 50 remaining) — Yellow warning in status bar
- **Critical** (< 10 remaining) — All API calls pause; cached data continues to display
- **Props guard** — Props fetching pauses at 3x the critical threshold since each sport requires multiple per-event API calls

## License

[MIT](LICENSE)
