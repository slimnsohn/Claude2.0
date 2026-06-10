"""Strategy plugin interface.

The same strategy classes run in backtest (driven by ReplayEngine), paper, and
live (driven by the orchestrator). Strategies see market data and their own
state, emit Intents, and never touch the exchange.

Parameter discipline: every tunable lives in DEFAULTS and may be overridden by
config within PARAM_BOUNDS. Self-tuning happens only inside those bounds —
that constraint is what keeps "self-learning" from becoming "self-rewriting".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from pmtrader.core.models import Fill, Intent, Market, OrderBook, Position

if TYPE_CHECKING:
    from pmtrader.datalayer.gamma import Event


@dataclass
class StrategyContext:
    """What a strategy may know about the world beyond market data."""
    now: float
    cash: float = 0.0
    budget: float = 0.0  # capital this strategy may deploy (allocator-set)
    positions: dict[str, Position] = field(default_factory=dict)
    open_order_count: int = 0
    get_market: Optional[Callable[[str], Optional[Market]]] = None

    def position_size(self, token_id: str) -> float:
        p = self.positions.get(token_id)
        return p.size if p else 0.0


class Strategy:
    name = "base"
    DEFAULTS: dict = {}
    PARAM_BOUNDS: dict = {}  # param -> (lo, hi); self-tuning must stay inside

    def __init__(self, params: dict | None = None):
        self.params = {**self.DEFAULTS, **(params or {})}
        for key, value in self.params.items():
            bounds = self.PARAM_BOUNDS.get(key)
            if bounds and not (bounds[0] <= value <= bounds[1]):
                raise ValueError(
                    f"{self.name}: param {key}={value} outside bounds {bounds}")

    def on_books(self, market: Market, books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        """Called when a market's books update. books keyed by token_id."""
        return []

    def on_event(self, event: "Event", books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        """Called for neg-risk multi-outcome events with all outcome books."""
        return []

    def on_fill(self, fill: Fill) -> None:
        """Own-fill notification (inventory, markout tracking)."""

    def on_timer(self, ctx: StrategyContext) -> list[Intent]:
        """Periodic housekeeping tick (requote, re-evaluate)."""
        return []
