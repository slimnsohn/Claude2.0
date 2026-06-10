"""S4 — calibration harvester.

Trades only price/category/time buckets where historical resolution data shows
the market is systematically miscalibrated by more than fees, with Wilson
lower-bound conservatism. The whitelist of tradeable buckets comes from
offline research (scripts/run_calibration_research.py) with walk-forward
validation — the strategy itself never invents buckets. Empty whitelist =
inert strategy, which is a valid (and honest) ship state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from pmtrader.core.fees import taker_fee_per_share
from pmtrader.core.models import Intent, Market, OrderBook, Side
from pmtrader.strategies.base import Strategy, StrategyContext

DTR_BANDS = [(7.0, "0-7d"), (30.0, "7-30d"), (float("inf"), "30d+")]


def dtr_band(days: float) -> str:
    for limit, name in DTR_BANDS:
        if days < limit:
            return name
    return "30d+"


def wilson_lower(wins: int, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound for a binomial proportion."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - spread)


@dataclass(frozen=True)
class Bucket:
    category: str
    price_decile: int  # int(price * 10), 0..9
    dtr_band: str


@dataclass
class BucketStats:
    n: int = 0
    wins: int = 0

    @property
    def hit_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def wilson_lo(self) -> float:
        return wilson_lower(self.wins, self.n)


def calibration_table(rows: list[tuple[str, float, float, bool]]) -> dict[Bucket, BucketStats]:
    """rows: (category, price, days_to_resolution, won)."""
    table: dict[Bucket, BucketStats] = {}
    for category, price, days, won in rows:
        decile = min(9, int(price * 10))
        b = Bucket(category=category, price_decile=decile, dtr_band=dtr_band(days))
        st = table.setdefault(b, BucketStats())
        st.n += 1
        st.wins += int(won)
    return table


def parse_end_date(end_date: str | None) -> float | None:
    if not end_date:
        return None
    try:
        return datetime.fromisoformat(end_date.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class S4Calib(Strategy):
    name = "s4_calib"
    DEFAULTS = {
        "margin": 0.005,           # required edge beyond wilson_lo - price - fees
        "max_market_notional": 200.0,  # tail risk is lumpy; tightest cap of all
        "min_bucket_n": 100,
    }
    PARAM_BOUNDS = {
        "margin": (0.001, 0.05),
        "max_market_notional": (10.0, 5_000.0),
        "min_bucket_n": (30, 100_000),
    }

    def __init__(self, params: dict | None = None,
                 whitelist: list[dict] | None = None):
        super().__init__(params)
        self.whitelist: dict[Bucket, dict] = {}
        for w in whitelist or []:
            if w.get("n", 0) >= self.params["min_bucket_n"]:
                b = Bucket(category=w["category"], price_decile=int(w["price_decile"]),
                           dtr_band=w["dtr_band"])
                self.whitelist[b] = w
        self.traded: set[str] = set()

    def on_books(self, market: Market, books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        if not self.whitelist or market.condition_id in self.traded:
            return []
        end_ts = parse_end_date(market.end_date)
        if end_ts is None:
            return []
        days = (end_ts - ctx.now) / 86400
        if days < 0:
            return []
        yes = books.get(market.token_id_yes)
        if yes is None or yes.best_ask is None:
            return []
        ask = yes.best_ask
        bucket = Bucket(category=market.category,
                        price_decile=min(9, int(ask * 10)),
                        dtr_band=dtr_band(days))
        entry = self.whitelist.get(bucket)
        if entry is None:
            return []
        fee = taker_fee_per_share(ask, schedule=market.fee_schedule,
                                  fees_enabled=market.fees_enabled)
        edge = entry["wilson_lo"] - ask - fee
        if edge < self.params["margin"]:
            return []
        max_shares = self.params["max_market_notional"] / ask
        size = float(int(min(max_shares, yes.best_ask_size, ctx.budget / ask)))
        if size < market.min_size:
            return []
        self.traded.add(market.condition_id)
        return [Intent(
            strategy=self.name, token_id=market.token_id_yes, side=Side.BUY,
            price=ask, size=size, expected_edge=edge,
            reasoning=(f"calibration bucket {bucket.category}/d{bucket.price_decile}/"
                       f"{bucket.dtr_band}: hist wilson_lo={entry['wilson_lo']:.4f} "
                       f"(n={entry['n']}) vs ask={ask:.3f} fee={fee:.4f} "
                       f"edge={edge:.4f}"),
            condition_id=market.condition_id)]

    def on_market_resolved(self, condition_id: str) -> None:
        self.traded.discard(condition_id)
