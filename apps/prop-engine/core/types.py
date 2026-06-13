from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class BookOdds:
    book: str
    american_odds: int
    fetched_at: datetime

    @property
    def decimal_odds(self) -> float:
        if self.american_odds >= 100:
            return 1.0 + self.american_odds / 100.0
        return 1.0 + 100.0 / abs(self.american_odds)

    @property
    def implied_prob(self) -> float:
        return 1.0 / self.decimal_odds


@dataclass(frozen=True)
class Market:
    event_id: str
    market_type: str
    player_name: str
    line_value: float
    side: str
    commence_time: datetime
    is_alternate: bool = False
    player_external_ids: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Features:
    player_id: str
    as_of: datetime
    stat_avg: dict
    stat_sigma: dict
    n_games: int
    is_b2b: bool
    rest_days: int
    usage_rate: float
    teammates_out: list
    position: str


@dataclass(frozen=True)
class ResidualAdjustment:
    rest: float = 0.0
    teammate_out: float = 0.0
    notes: tuple = ()

    @property
    def total(self) -> float:
        return self.rest + self.teammate_out


@dataclass(frozen=True)
class Play:
    market: Market
    book: str
    offered_odds: int
    posterior_prob: float
    edge_pct: float
    recommended_stake: float
    ev_dollars: float
    sigma_used: float
    consensus_prob: float
    mu_implied: float
    mu_adjusted: float
    residual: ResidualAdjustment
    notes: tuple = ()
