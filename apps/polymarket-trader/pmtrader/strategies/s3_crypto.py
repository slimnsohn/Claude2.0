"""S3 — crypto fair value: price binary crypto markets as short-dated options.

Fair value of "spot above K at T" under driftless lognormal:
    P = Phi( ln(S/K) / (sigma * sqrt(tau)) )
sigma from EWMA realized vol on Coinbase 1m closes. Trade only when the
market diverges from fair by more than fees + half-spread + margin, with a
vol-of-vol guard that widens the margin when the vol estimate itself is
unstable (model risk discipline: when unsure of sigma, demand more edge).

v1 scope: markets with an explicit strike in the question ("above $X",
"reach $X", "below $X"). Up/down period markets need an observed period-open
price; they are skipped unless a strike was injected via set_strike().
"""
from __future__ import annotations

import math
import re
from collections import deque

from pmtrader.core.fees import taker_fee_per_share
from pmtrader.core.models import Intent, Market, OrderBook, Side
from pmtrader.strategies.base import Strategy, StrategyContext
from pmtrader.strategies.s4_calib import parse_end_date

YEAR_SECONDS = 365.0 * 86_400
MINUTES_PER_YEAR = 365 * 24 * 60


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def fair_value(spot: float, strike: float, sigma_ann: float,
               tau_years: float) -> float:
    """P(S_T > K) driftless lognormal."""
    if tau_years <= 0 or sigma_ann <= 0:
        return 1.0 if spot > strike else 0.0
    d = math.log(spot / strike) / (sigma_ann * math.sqrt(tau_years))
    return phi(d)


def ewma_vol_annualized(closes: list[tuple[float, float]],
                        lam: float = 0.94) -> float | None:
    """closes: [(ts, close)] 1-minute candles, oldest first."""
    if len(closes) < 2:
        return None
    rets = [math.log(closes[i][1] / closes[i - 1][1])
            for i in range(1, len(closes))]
    var = rets[0] ** 2
    for r in rets[1:]:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var * MINUTES_PER_YEAR)


STRIKE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*([kKmM]?)")
BELOW_WORDS = ("below", "under", "dip", "drop", "fall", "less than")
ABOVE_WORDS = ("above", "reach", "hit", "exceed", "over", "more than",
               "close at or above", "at or above")
ASSET_WORDS = {"bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH",
               "solana": "SOL", "sol": "SOL", "xrp": "XRP", "dogecoin": "DOGE"}


def parse_strike(question: str) -> tuple[float, str] | None:
    m = STRIKE_RE.search(question)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    suffix = m.group(2).lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    q = question.lower()
    if any(w in q for w in BELOW_WORDS):
        return value, "below"
    if any(w in q for w in ABOVE_WORDS):
        return value, "above"
    return None


def parse_asset(question: str) -> str | None:
    q = question.lower()
    for word, symbol in ASSET_WORDS.items():
        if word in q:
            return symbol
    return None


class S3Crypto(Strategy):
    name = "s3_crypto"
    DEFAULTS = {
        "margin": 0.02,             # required edge beyond fees + half-spread
        "max_notional": 250.0,      # per market
        "vol_of_vol_guard": 0.25,   # rel. std of recent vol ests that doubles margin
        "vol_history": 12,          # recent vol estimates tracked
        "maker_spread_threshold": 0.04,  # spread wider than this -> post inside
        "max_tau_days": 45.0,
    }
    PARAM_BOUNDS = {
        "margin": (0.002, 0.2), "max_notional": (10.0, 10_000.0),
        "vol_of_vol_guard": (0.01, 2.0), "vol_history": (3, 200),
        "maker_spread_threshold": (0.005, 0.5), "max_tau_days": (0.01, 365.0),
    }

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.spot: dict[str, float] = {}
        self.vol: dict[str, float] = {}
        self.vol_history: dict[str, deque] = {}
        self.strikes: dict[str, tuple[float, str]] = {}  # condition_id overrides
        self.traded: set[str] = set()

    # -- data wiring -------------------------------------------------------------
    def update_spot(self, asset: str, spot: float,
                    vol_annualized: float | None = None) -> None:
        self.spot[asset] = spot
        if vol_annualized is not None:
            self.vol[asset] = vol_annualized
            hist = self.vol_history.setdefault(
                asset, deque(maxlen=int(self.params["vol_history"])))
            hist.append(vol_annualized)

    def set_strike(self, condition_id: str, strike: float,
                   direction: str = "above") -> None:
        self.strikes[condition_id] = (strike, direction)

    def _vol_unstable(self, asset: str) -> bool:
        hist = self.vol_history.get(asset)
        if not hist or len(hist) < 4:
            return False
        mean = sum(hist) / len(hist)
        if mean <= 0:
            return True
        var = sum((v - mean) ** 2 for v in hist) / (len(hist) - 1)
        return math.sqrt(var) / mean > self.params["vol_of_vol_guard"]

    # -- trading --------------------------------------------------------------------
    def on_books(self, market: Market, books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        if market.condition_id in self.traded:
            return []
        asset = parse_asset(market.question)
        if asset is None or asset not in self.spot or asset not in self.vol:
            return []
        parsed = self.strikes.get(market.condition_id) or \
            parse_strike(market.question)
        if parsed is None:
            return []
        strike, direction = parsed
        end_ts = parse_end_date(market.end_date)
        if end_ts is None:
            return []
        tau_years = (end_ts - ctx.now) / YEAR_SECONDS
        if tau_years <= 0 or tau_years > self.params["max_tau_days"] / 365:
            return []

        fair_above = fair_value(self.spot[asset], strike, self.vol[asset],
                                tau_years)
        fair_yes = fair_above if direction == "above" else 1.0 - fair_above

        margin = self.params["margin"]
        if self._vol_unstable(asset):
            margin *= 2.0

        yes_book = books.get(market.token_id_yes)
        no_book = books.get(market.token_id_no)
        if yes_book is None or no_book is None:
            return []

        # candidate trades: buy YES if market underprices it; buy NO if it
        # overprices YES (we cannot short tokens)
        for token_id, book, fair in (
                (market.token_id_yes, yes_book, fair_yes),
                (market.token_id_no, no_book, 1.0 - fair_yes)):
            ask = book.best_ask
            if ask is None or book.spread is None:
                continue
            half_spread = book.spread / 2
            fee = taker_fee_per_share(ask, schedule=market.fee_schedule,
                                      fees_enabled=market.fees_enabled)
            edge = fair - ask - fee - margin
            if edge <= 0:
                continue
            wide = book.spread > self.params["maker_spread_threshold"]
            if wide and book.best_bid is not None:
                price = min(round(book.best_bid + market.tick_size, 4),
                            ask - market.tick_size)
                post_only = True
                edge = fair - price - margin  # maker pays no fee
            else:
                price = ask
                post_only = False
            size = float(int(min(self.params["max_notional"] / price,
                                 book.best_ask_size or 0,
                                 ctx.budget / price)))
            if size < market.min_size:
                continue
            self.traded.add(market.condition_id)
            return [Intent(
                strategy=self.name, token_id=token_id, side=Side.BUY,
                price=price, size=size, expected_edge=edge,
                post_only=post_only,
                reasoning=(f"s3 {asset} spot={self.spot[asset]:.0f} "
                           f"K={strike:.0f} {direction} sigma={self.vol[asset]:.3f} "
                           f"tau={tau_years * 365:.2f}d fair={fair:.4f} "
                           f"ask={ask:.3f} fee={fee:.4f} margin={margin:.3f} "
                           f"edge={edge:.4f} {'maker' if post_only else 'taker'}"),
                condition_id=market.condition_id, event_id=market.event_id)]
        return []

    def on_market_resolved(self, condition_id: str) -> None:
        self.traded.discard(condition_id)
        self.strikes.pop(condition_id, None)
