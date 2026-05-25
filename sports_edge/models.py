from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FORMAT)


def iso_dt(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


@dataclass(frozen=True)
class OddsSnapshot:
    event_id: str
    sport: str
    league: str
    event_date: datetime
    home_team: str
    away_team: str
    market: str
    selection: str
    side: str
    snapshot_time: datetime
    american_odds: int
    is_closing: bool
    winner: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "OddsSnapshot":
        return cls(
            event_id=row["event_id"],
            sport=row["sport"],
            league=row["league"],
            event_date=parse_dt(row["event_date"]),
            home_team=row["home_team"],
            away_team=row["away_team"],
            market=row["market"],
            selection=row["selection"],
            side=row["side"],
            snapshot_time=parse_dt(row["snapshot_time"]),
            american_odds=int(row["american_odds"]),
            is_closing=row["is_closing"].strip().lower() == "true",
            winner=row["winner"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sport": self.sport,
            "league": self.league,
            "event_date": iso_dt(self.event_date),
            "home_team": self.home_team,
            "away_team": self.away_team,
            "market": self.market,
            "selection": self.selection,
            "side": self.side,
            "snapshot_time": iso_dt(self.snapshot_time),
            "american_odds": self.american_odds,
            "is_closing": self.is_closing,
            "winner": self.winner,
        }


@dataclass(frozen=True)
class NewsItem:
    event_id: str
    published_at: datetime
    target_team: str
    source: str
    headline: str
    sentiment: float
    impact_score: float
    tags: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "NewsItem":
        return cls(
            event_id=row["event_id"],
            published_at=parse_dt(row["published_at"]),
            target_team=row["target_team"],
            source=row["source"],
            headline=row["headline"],
            sentiment=float(row["sentiment"]),
            impact_score=float(row["impact_score"]),
            tags=row["tags"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "published_at": iso_dt(self.published_at),
            "target_team": self.target_team,
            "source": self.source,
            "headline": self.headline,
            "sentiment": self.sentiment,
            "impact_score": self.impact_score,
            "tags": self.tags,
        }


@dataclass(frozen=True)
class TeamStats:
    team: str
    league: str
    rating: float
    recent_form: float
    offense: float
    defense: float
    injury_penalty: float
    rest_advantage: float

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "TeamStats":
        return cls(
            team=row["team"],
            league=row["league"],
            rating=float(row["rating"]),
            recent_form=float(row["recent_form"]),
            offense=float(row["offense"]),
            defense=float(row["defense"]),
            injury_penalty=float(row["injury_penalty"]),
            rest_advantage=float(row["rest_advantage"]),
        )

    @property
    def adjusted_rating(self) -> float:
        return (
            self.rating
            + (self.recent_form * 4.0)
            + (self.offense * 1.5)
            - (self.defense * 1.2)
            - self.injury_penalty
            + self.rest_advantage
        )


@dataclass(frozen=True)
class Forecast:
    event_id: str
    sport: str
    league: str
    event_date: str
    matchup: str
    selection: str
    side: str
    american_odds: int
    implied_probability: float
    fair_probability: float
    confidence: float
    expected_value: float
    movement_score: float
    news_score: float
    stats_edge: float
    decision: str
    stake_units: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class TradeRecord:
    decision_id: str
    created_at: str
    mode: str
    event_id: str
    league: str
    matchup: str
    selection: str
    side: str
    american_odds: int
    implied_probability: float
    fair_probability: float
    confidence: float
    expected_value: float
    stake_units: float
    outcome: str
    pnl_units: float
    bankroll_after: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
