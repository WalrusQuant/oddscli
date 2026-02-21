"""Load .env and settings.yaml, expose all configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


def _load_yaml() -> dict:
    settings_path = PROJECT_ROOT / "settings.yaml"
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError:
            log.warning("Failed to parse settings.yaml, using defaults")
            return {}
    return {}


class Settings(BaseModel):
    api_key: str = ""

    @field_validator("api_key")
    @classmethod
    def strip_api_key(cls, v: str) -> str:
        return v.strip()
    bookmakers: list[str] = Field(default_factory=lambda: ["fanduel", "draftkings"])
    ev_reference: str = "market_average"
    sports: list[str] = Field(
        default_factory=lambda: [
            "americanfootball_nfl",
            "basketball_nba",
            "baseball_mlb",
            "icehockey_nhl",
        ]
    )
    odds_refresh_interval: int = 300
    scores_refresh_interval: int = 120
    ev_threshold: float = 2.0
    ev_odds_min: float = -200
    ev_odds_max: float = 200
    odds_format: str = "american"
    regions: list[str] = Field(default_factory=lambda: ["us", "us2", "us_ex"])
    low_credit_warning: int = 50
    critical_credit_stop: int = 10
    props_enabled: bool = True
    props_refresh_interval: int = 300
    props_max_concurrent: int = 5
    # DFS books: book_key → effective odds for your lineup type.
    # API always returns a fixed juice (e.g. -137) but actual odds depend on legs.
    alt_lines_enabled: bool = False
    arb_enabled: bool = True
    arb_min_profit_pct: float = 0.1
    middle_enabled: bool = True
    middle_min_window: float = 0.5
    middle_max_combined_cost: float = 1.08
    dfs_books: dict[str, float] = Field(default_factory=dict)
    props_markets: dict[str, list[str]] = Field(default_factory=lambda: {
        "americanfootball_nfl": [
            "player_pass_yds", "player_pass_tds", "player_rush_yds",
            "player_reception_yds", "player_receptions", "player_anytime_td",
        ],
        "basketball_nba": [
            "player_points", "player_rebounds", "player_assists",
            "player_threes", "player_points_rebounds_assists",
        ],
        "baseball_mlb": [
            "batter_home_runs", "batter_hits", "batter_total_bases",
            "pitcher_strikeouts",
        ],
        "icehockey_nhl": [
            "player_points", "player_goals", "player_assists",
            "player_shots_on_goal",
        ],
    })

    @property
    def regions_str(self) -> str:
        """Comma-separated regions for API calls."""
        return ",".join(self.regions)


def load_settings() -> Settings:
    _load_env()
    raw = _load_yaml()
    raw["api_key"] = os.getenv("ODDS_API_KEY", "")
    return Settings(**raw)
