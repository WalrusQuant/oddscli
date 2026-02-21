"""Pydantic models for Odds API responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Sport(BaseModel):
    key: str
    group: str
    title: str
    description: str = ""
    active: bool = True
    has_outrights: bool = False


class OutcomeOdds(BaseModel):
    name: str
    price: float
    point: float | None = None
    description: str | None = None


class Market(BaseModel):
    key: str  # h2h, spreads, totals
    last_update: datetime | None = None
    outcomes: list[OutcomeOdds] = Field(default_factory=list)


class Bookmaker(BaseModel):
    key: str
    title: str
    last_update: datetime | None = None
    markets: list[Market] = Field(default_factory=list)


class Event(BaseModel):
    id: str
    sport_key: str
    sport_title: str = ""
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: list[Bookmaker] = Field(default_factory=list)


class ScoreValue(BaseModel):
    name: str
    score: str | None = None


class Score(BaseModel):
    id: str
    sport_key: str
    sport_title: str = ""
    commence_time: datetime
    home_team: str
    away_team: str
    completed: bool = False
    last_update: datetime | None = None
    scores: list[ScoreValue] | None = None

    def home_score(self) -> str:
        if self.scores:
            for s in self.scores:
                if s.name == self.home_team and s.score is not None:
                    return s.score
        return "-"

    def away_score(self) -> str:
        if self.scores:
            for s in self.scores:
                if s.name == self.away_team and s.score is not None:
                    return s.score
        return "-"


class GameRow(BaseModel):
    """Merged view of a game with scores and odds."""

    event_id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: datetime
    home_score: str = "-"
    away_score: str = "-"
    completed: bool = False
    bookmakers: list[Bookmaker] = Field(default_factory=list)


class PropRow(BaseModel):
    """Display-ready model for a player prop line (paired Over/Under)."""

    event_id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: datetime
    player_name: str
    market_key: str
    consensus_point: float | None = None
    over_odds: dict[str, float] = Field(default_factory=dict)   # book_key -> price
    under_odds: dict[str, float] = Field(default_factory=dict)  # book_key -> price
