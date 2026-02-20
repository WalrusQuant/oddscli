"""Load .env and settings.yaml, expose all configuration."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


def _load_yaml() -> dict:
    settings_path = PROJECT_ROOT / "settings.yaml"
    if settings_path.exists():
        with open(settings_path) as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseModel):
    api_key: str = ""
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
    odds_format: str = "american"
    regions: list[str] = Field(default_factory=lambda: ["us", "us2", "us_ex"])
    low_credit_warning: int = 50
    critical_credit_stop: int = 10

    @property
    def regions_str(self) -> str:
        """Comma-separated regions for API calls."""
        return ",".join(self.regions)


def load_settings() -> Settings:
    _load_env()
    raw = _load_yaml()
    raw["api_key"] = os.getenv("ODDS_API_KEY", "")
    return Settings(**raw)
