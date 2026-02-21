"""OddsTickerApp — top-level Textual application."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from app.config import Settings, load_settings
from app.services.data_service import DataService
from app.ui.widgets.ev_panel import EVPanel
from app.ui.widgets.games_table import GamesTicker
from app.ui.widgets.props_table import PropsTable
from app.ui.widgets.sport_tabs import SportTabs
from app.ui.widgets.status_bar import StatusBar

log = logging.getLogger(__name__)

CSS_PATH = Path(__file__).parent / "styles.tcss"


class OddsTickerApp(App):
    """Live Sports Odds & Scores Terminal Ticker."""

    TITLE = "OddsCLI"
    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("right", "next_sport", "Next Sport", show=False),
        Binding("left", "prev_sport", "Prev Sport", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("m", "toggle_market", "Market", show=False),
        Binding("e", "toggle_ev", "Toggle EV", show=False),
        Binding("p", "toggle_props", "Props", show=False),
        Binding("s", "toggle_settings", "Settings", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings: Settings = load_settings()
        self.data_service = DataService(self.settings)
        self._current_sport: str = ""
        self._scores_timer = None
        self._odds_timer = None
        self._props_timer = None
        self._init_done = False  # True after initial setup completes
        self._view_mode: str = "games"  # "games" or "props"

    def compose(self) -> ComposeResult:
        yield SportTabs(self.settings.sports, id="sport-tabs")
        yield GamesTicker(id="games-ticker")
        yield PropsTable(id="props-table")
        yield EVPanel(id="ev-panel")
        yield Static(" ", id="settings-panel")
        yield StatusBar(id="status-bar")

    async def on_mount(self) -> None:
        if not self.settings.api_key:
            status = self.query_one("#status-bar", StatusBar)
            status.set_warning("No API key! Add ODDS_API_KEY to .env")
            ticker = self.query_one("#games-ticker", GamesTicker)
            try:
                content = ticker.query_one("#games-content", Static)
                content.update(
                    "[bold red]No API key configured.[/bold red]\n"
                    "Add your key to .env: ODDS_API_KEY=your_key_here\n"
                    "Get a free key at https://the-odds-api.com/"
                )
            except Exception:
                pass
            return

        # Configure display books and DFS overrides for both tickers
        ticker = self.query_one("#games-ticker", GamesTicker)
        ticker.set_display_books(self.settings.bookmakers)
        ticker.set_dfs_books(self.settings.dfs_books)

        props_table = self.query_one("#props-table", PropsTable)
        props_table.set_display_books(self.settings.bookmakers)

        # Run full initialization as a worker so it doesn't block
        # the message loop (which would prevent widgets from composing)
        self.run_worker(self._initialize(), exclusive=True, group="init")

    async def _initialize(self) -> None:
        """Filter sports, load initial data, start timers."""
        tabs = self.query_one("#sport-tabs", SportTabs)

        active_sports = await self._filter_active_sports(self.settings.sports)
        if not active_sports:
            return

        tabs.sports = active_sports
        tabs._render_tabs()

        self._current_sport = active_sports[0]
        self._init_done = True  # Now safe to accept sport-change events

        # Load initial data
        await self._load_data()

        # Start auto-refresh timers
        self._scores_timer = self.set_interval(
            self.settings.scores_refresh_interval, self._auto_refresh_scores
        )
        self._odds_timer = self.set_interval(
            self.settings.odds_refresh_interval, self._auto_refresh_odds
        )
        self._props_timer = self.set_interval(
            self.settings.props_refresh_interval, self._auto_refresh_props
        )

    async def _filter_active_sports(self, wanted: list[str]) -> list[str]:
        try:
            api_sports = await self.data_service.fetch_sports()
            active_keys = {s.key for s in api_sports if s.active}
            return [s for s in wanted if s in active_keys]
        except Exception:
            log.exception("Failed to check active sports, showing all")
            return wanted

    async def on_unmount(self) -> None:
        await self.data_service.close()

    async def on_sport_tabs_changed(self, event: SportTabs.Changed) -> None:
        if not self._init_done:
            return  # Ignore events during initialization
        if event.sport_key == self._current_sport:
            return  # Already on this sport
        self._current_sport = event.sport_key
        if self._view_mode == "props":
            self.run_worker(self._load_props(), exclusive=True, group="load")
        else:
            self.run_worker(self._load_data(), exclusive=True, group="load")

    def action_next_sport(self) -> None:
        self.query_one("#sport-tabs", SportTabs).next_sport()

    def action_prev_sport(self) -> None:
        self.query_one("#sport-tabs", SportTabs).prev_sport()

    def action_refresh(self) -> None:
        if self._current_sport:
            self.data_service.force_refresh(self._current_sport)
            if self._view_mode == "props":
                self.run_worker(self._load_props(), exclusive=True, group="load")
            else:
                self.run_worker(self._load_data(), exclusive=True, group="load")

    def action_toggle_market(self) -> None:
        if self._view_mode == "props":
            self.query_one("#props-table", PropsTable).cycle_filter()
        else:
            self.query_one("#games-ticker", GamesTicker).toggle_market()

    def action_toggle_ev(self) -> None:
        self.query_one("#ev-panel", EVPanel).toggle()

    def action_toggle_props(self) -> None:
        """Switch between games view and props view."""
        ticker = self.query_one("#games-ticker", GamesTicker)
        props = self.query_one("#props-table", PropsTable)

        if self._view_mode == "games":
            self._view_mode = "props"
            ticker.display = False
            props.add_class("visible")
            # Load props data
            if self._current_sport:
                self.run_worker(self._load_props(), exclusive=True, group="load")
        else:
            self._view_mode = "games"
            ticker.display = True
            props.remove_class("visible")
            # Reload game data + game EV
            if self._current_sport:
                self.run_worker(self._load_data(), exclusive=True, group="load")

    def action_toggle_settings(self) -> None:
        panel = self.query_one("#settings-panel", Static)
        if panel.has_class("visible"):
            panel.remove_class("visible")
        else:
            panel.add_class("visible")
            self._render_settings_panel()

    def _render_settings_panel(self) -> None:
        s = self.settings
        text = (
            "[bold]Settings[/bold] (edit settings.yaml)\n\n"
            f"[bold]Regions:[/bold] {', '.join(s.regions)}\n"
            f"[bold]Bookmakers:[/bold] ({len(s.bookmakers)})\n"
            + "\n".join(f"  - {b}" for b in s.bookmakers)
            + f"\n\n[bold]EV Reference:[/bold] {s.ev_reference}"
            f"\n[bold]EV Threshold:[/bold] {s.ev_threshold}%"
            f"\n[bold]Odds Format:[/bold] {s.odds_format}"
            f"\n\n[bold]Refresh:[/bold]"
            f"\n  Scores: {s.scores_refresh_interval}s"
            f"\n  Odds: {s.odds_refresh_interval}s"
            f"\n  Props: {s.props_refresh_interval}s"
        )
        self.query_one("#settings-panel", Static).update(text)

    async def _load_data(self) -> None:
        if not self._current_sport:
            return

        sport = self._current_sport
        log.info("Loading data for %s", sport)

        ticker = self.query_one("#games-ticker", GamesTicker)
        status = self.query_one("#status-bar", StatusBar)
        ev_panel = self.query_one("#ev-panel", EVPanel)

        try:
            games = await self.data_service.get_game_rows(sport)
            log.info("Got %d games for %s", len(games), sport)

            await self.data_service.get_ev_bets(sport)

            ticker.update_games(games)

            store_rows = self.data_service.get_ev_for_sport(sport)
            ev_panel.update_from_store(store_rows)

            status.update_credits(self.data_service.budget)
            status.update_refresh_time()

        except Exception as e:
            log.exception("Error loading data for %s", sport)
            try:
                content = ticker.query_one("#games-content", Static)
                content.update(f"[bold red]Error: {e}[/bold red]")
            except Exception:
                pass

    async def _load_props(self) -> None:
        """Fetch prop rows, run prop EV, and update widgets."""
        if not self._current_sport:
            return

        sport = self._current_sport
        log.info("Loading props for %s", sport)

        props_table = self.query_one("#props-table", PropsTable)
        status = self.query_one("#status-bar", StatusBar)
        ev_panel = self.query_one("#ev-panel", EVPanel)

        try:
            # Set sport-specific filter keys before loading data
            sport_markets = self.settings.props_markets.get(sport, [])
            props_table.set_sport(sport, sport_markets)

            events = await self.data_service.fetch_props(sport)
            prop_rows = self.data_service.get_prop_rows(events)
            log.info("Got %d prop rows for %s", len(prop_rows), sport)

            await self.data_service.get_prop_ev_bets(sport)

            props_table.update_props(prop_rows)

            store_rows = self.data_service.get_prop_ev_for_sport(sport)
            ev_panel.update_from_store(store_rows)

            status.update_credits(self.data_service.budget)
            status.update_refresh_time()

        except Exception as e:
            log.exception("Error loading props for %s", sport)
            try:
                content = props_table.query_one("#props-content", Static)
                content.update(f"[bold red]Error: {e}[/bold red]")
            except Exception:
                pass

    async def _auto_refresh_scores(self) -> None:
        if self._current_sport and self._view_mode == "games":
            self.data_service.cache.invalidate(f"{self._current_sport}:scores")
            self.run_worker(self._load_data(), exclusive=True, group="load")

    async def _auto_refresh_odds(self) -> None:
        if self._current_sport and self._view_mode == "games":
            self.data_service.cache.invalidate(f"{self._current_sport}:odds")
            self.run_worker(self._load_data(), exclusive=True, group="load")

    async def _auto_refresh_props(self) -> None:
        if self._current_sport and self._view_mode == "props":
            self.data_service.cache.invalidate(f"{self._current_sport}:props")
            self.run_worker(self._load_props(), exclusive=True, group="load")
