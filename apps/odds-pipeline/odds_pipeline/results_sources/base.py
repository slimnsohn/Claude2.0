"""Base interface for per-sport results adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date


@dataclass
class GameResult:
    sport: str
    commence_time: datetime
    home_team_canonical: str
    away_team_canonical: str
    source_game_id: str
    segment_scores: dict[str, tuple[int, int]]   # {'Q1': (24,28), 'FULL': (108,102), ...}
    went_to_ot: bool
    raw_payload: dict = field(default_factory=dict)


class ResultsAdapter(ABC):
    sport: str = ""
    segments: list[str] = []

    @abstractmethod
    def fetch_completed_games(self, date_from: date, date_to: date) -> list[GameResult]:
        ...
