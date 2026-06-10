"""Conservative transaction-cost model for backtests.

Real books are not reconstructable from sampled price history, so costs are
deliberately pessimistic: takers pay an assumed half-spread plus slippage plus
the market's fee schedule; makers earn no rebates and fill only on strict
price-through (enforced by the replay engine, not here).
"""
from __future__ import annotations

from pmtrader.core.fees import order_taker_fee
from pmtrader.core.models import Market, Side


class CostModel:
    def __init__(self, half_spread: float = 0.01, slippage_bps: float = 50.0):
        self.half_spread = half_spread
        self.slippage_bps = slippage_bps

    def synthetic_quote(self, mid: float, side: Side) -> float:
        """Price a taker actually gets when the sampled mid is `mid`."""
        if side == Side.BUY:
            return min(0.999, mid + self.half_spread)
        return max(0.001, mid - self.half_spread)

    def taker_fill_cost(self, market: Market, side: Side, price: float,
                        size: float) -> tuple[float, float]:
        """Returns (cash_delta, fee). BUY: cash_delta negative."""
        notional = price * size
        slippage = notional * self.slippage_bps / 10_000
        fee = order_taker_fee(price, size, schedule=market.fee_schedule,
                              fees_enabled=market.fees_enabled)
        if side == Side.BUY:
            return (-(notional + slippage + fee), fee)
        return (notional - slippage - fee, fee)

    def maker_fill_cost(self, market: Market, side: Side, price: float,
                        size: float) -> tuple[float, float]:
        """Makers pay no fee and no slippage (rebates conservatively ignored)."""
        notional = price * size
        return (-notional if side == Side.BUY else notional, 0.0)
