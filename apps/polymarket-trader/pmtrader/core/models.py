"""Core domain models. Every other module speaks these types."""
from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from pmtrader.core.fees import FeeSchedule


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(StrEnum):
    GTC = "GTC"  # good till cancelled
    IOC = "IOC"  # immediate or cancel (take what's there, cancel rest)
    GTD = "GTD"  # good till date


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Level(BaseModel):
    price: float = Field(gt=0, lt=1)
    size: float = Field(ge=0)


class OrderBook(BaseModel):
    token_id: str
    ts: float
    bids: list[Level]
    asks: list[Level]

    @property
    def _sorted_bids(self) -> list[Level]:
        return sorted(self.bids, key=lambda l: l.price, reverse=True)

    @property
    def _sorted_asks(self) -> list[Level]:
        return sorted(self.asks, key=lambda l: l.price)

    @property
    def best_bid(self) -> Optional[float]:
        return self._sorted_bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self._sorted_asks[0].price if self.asks else None

    @property
    def best_bid_size(self) -> Optional[float]:
        return self._sorted_bids[0].size if self.bids else None

    @property
    def best_ask_size(self) -> Optional[float]:
        return self._sorted_asks[0].size if self.asks else None

    @property
    def mid(self) -> Optional[float]:
        if not self.bids or not self.asks:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def microprice(self) -> Optional[float]:
        """Depth-weighted mid: leans toward the side with less resting size."""
        if not self.bids or not self.asks:
            return None
        bid_sz, ask_sz = self.best_bid_size, self.best_ask_size
        total = bid_sz + ask_sz
        if total == 0:
            return self.mid
        return (self.best_bid * ask_sz + self.best_ask * bid_sz) / total

    @property
    def spread(self) -> Optional[float]:
        if not self.bids or not self.asks:
            return None
        return self.best_ask - self.best_bid

    def ask_depth_at_or_below(self, price: float) -> float:
        return sum(l.size for l in self.asks if l.price <= price)

    def bid_depth_at_or_above(self, price: float) -> float:
        return sum(l.size for l in self.bids if l.price >= price)


class Market(BaseModel):
    condition_id: str
    question: str
    category: str = "unknown"
    token_id_yes: str
    token_id_no: str
    neg_risk: bool = False
    neg_risk_market_id: str = ""
    end_date: Optional[str] = None
    fee_schedule: Optional[FeeSchedule] = None
    fees_enabled: bool = True  # conservative default: assume fees apply
    tick_size: float = 0.01
    min_size: float = 5.0
    active: bool = True
    volume_24h: float = 0.0
    rewards_enabled: bool = False
    event_id: Optional[str] = None


class Intent(BaseModel):
    """A strategy's wish to trade. Strategies emit these; only execution acts."""
    strategy: str
    token_id: str
    side: Side
    price: float = Field(gt=0, lt=1)
    size: float = Field(gt=0)
    expected_edge: float  # per-share, fee-adjusted, may be negative for unwinds
    reasoning: str = Field(min_length=1)
    tif: TimeInForce = TimeInForce.GTC
    post_only: bool = False
    group_id: Optional[str] = None  # atomic multi-leg groups (arb legs)
    condition_id: Optional[str] = None
    event_id: Optional[str] = None


class Order(BaseModel):
    id: str
    intent: Intent
    status: OrderStatus
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    created_ts: float
    updated_ts: float
    exchange_id: Optional[str] = None  # id assigned by CLOB

    @property
    def remaining(self) -> float:
        return self.intent.size - self.filled_size


class Fill(BaseModel):
    order_id: str
    token_id: str
    side: Side
    price: float = Field(gt=0, lt=1)
    size: float = Field(gt=0)
    fee: float = 0.0
    ts: float
    maker: bool = False

    @property
    def notional(self) -> float:
        return self.price * self.size


class Position(BaseModel):
    token_id: str
    size: float  # signed: + long shares
    avg_cost: float
    condition_id: Optional[str] = None
    event_id: Optional[str] = None

    def mark_value(self, mark: float) -> float:
        return self.size * mark

    def unrealized_pnl(self, mark: float) -> float:
        return self.size * (mark - self.avg_cost)
