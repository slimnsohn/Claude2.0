"""S2 — market maker: spread capture + maker rebates, Avellaneda-Stoikov-lite.

Quotes both sides of YES around a microprice reference, spread set by recent
reference volatility, quotes skewed against inventory. The self-defense layer
is markout tracking: P&L of recent fills measured against the mid 30s later.
Persistent negative markout = informed flow is picking us off -> widen, then
pull. Fee model: maker orders pay nothing and earn rebates (not modeled in
EV — treated as bonus, never as the edge).
"""
from __future__ import annotations

import math
from collections import defaultdict, deque

from pmtrader.core.models import Intent, Market, OrderBook, Side
from pmtrader.strategies.base import Strategy, StrategyContext
from pmtrader.strategies.s4_calib import parse_end_date


class S2MarketMaker(Strategy):
    name = "s2_mm"
    DEFAULTS = {
        "gamma": 0.0005,          # inventory aversion ($ skew per share per σ²τ unit)
        "k_spread": 6.0,          # half-spread = max(min_half, k * σ_ref)
        "min_spread": 0.02,       # full spread floor
        "max_spread": 0.20,
        "quote_size": 100.0,
        "max_inventory": 500.0,   # shares per token
        "markout_threshold": -0.005,   # avg $/share markout that triggers widening
        "markout_window": 20,     # fills
        "markout_horizon": 30.0,  # seconds
        "vol_window": 20,         # reference samples for EWMA vol
        "vol_lambda": 0.94,
        "requote_tick": 0.005,    # reference move that forces requote
        "min_volume_24h": 5_000.0,
        "min_hours_to_end": 48.0,
    }
    PARAM_BOUNDS = {
        "gamma": (0.0, 0.1), "k_spread": (0.5, 50.0),
        "min_spread": (0.005, 0.10), "max_spread": (0.02, 0.5),
        "quote_size": (5.0, 10_000.0), "max_inventory": (10.0, 100_000.0),
        "markout_threshold": (-0.10, 0.0), "markout_window": (5, 200),
        "markout_horizon": (5.0, 600.0), "vol_window": (5, 500),
        "vol_lambda": (0.5, 0.999), "requote_tick": (0.001, 0.05),
        "min_volume_24h": (0.0, 1e9), "min_hours_to_end": (0.0, 24 * 30),
    }

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.refs: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=int(self.params["vol_window"])))
        self.ewma_var: dict[str, float] = {}
        self.last_quote_ref: dict[str, float] = {}
        self.last_quote_inv: dict[str, float] = {}
        self.pending_markouts: dict[str, list] = defaultdict(list)  # token -> [(ts, side, price)]
        self.markouts: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=int(self.params["markout_window"])))
        self.widen_mult: dict[str, float] = defaultdict(lambda: 1.0)

    # -- selection ---------------------------------------------------------------
    def select_markets(self, candidates: list[Market], now: float) -> list[Market]:
        out = []
        for m in candidates:
            if m.volume_24h < self.params["min_volume_24h"]:
                continue
            if not m.rewards_enabled:
                continue
            end_ts = parse_end_date(m.end_date)
            if end_ts is None or \
                    end_ts - now < self.params["min_hours_to_end"] * 3600:
                continue
            out.append(m)
        return out

    # -- markout tracking ----------------------------------------------------------
    def on_fill(self, fill) -> None:
        self.pending_markouts[fill.token_id].append(
            (fill.ts, fill.side, fill.price))

    def _settle_markouts(self, token_id: str, mid: float, now: float) -> None:
        horizon = self.params["markout_horizon"]
        still = []
        for ts, side, price in self.pending_markouts[token_id]:
            if now - ts >= horizon:
                pnl = (mid - price) if side == Side.BUY else (price - mid)
                self.markouts[token_id].append(pnl)
            else:
                still.append((ts, side, price))
        self.pending_markouts[token_id] = still

    def markout_avg(self, token_id: str) -> float:
        xs = self.markouts[token_id]
        return sum(xs) / len(xs) if xs else 0.0

    # -- quoting ----------------------------------------------------------------------
    def on_books(self, market: Market, books: dict[str, OrderBook],
                 ctx: StrategyContext) -> list[Intent]:
        token = market.token_id_yes
        book = books.get(token)
        if book is None or book.microprice is None:
            return []
        ref = book.microprice
        self._update_vol(token, ref)
        self._settle_markouts(token, book.mid, ctx.now)

        if len(self.refs[token]) < self.params["vol_window"]:
            return []

        # markout defense: widen on bad markouts, pull on very bad
        avg_markout = self.markout_avg(token)
        threshold = self.params["markout_threshold"]
        if len(self.markouts[token]) >= 5:
            if avg_markout < 2 * threshold:
                self.widen_mult[token] = 0.0  # pulled
            elif avg_markout < threshold:
                self.widen_mult[token] = 2.0
            else:
                self.widen_mult[token] = 1.0
        if self.widen_mult[token] == 0.0:
            return []

        # Two-sided quoting on a binary market: you cannot sell tokens you
        # don't hold, so the "ask" on YES is expressed as a BID on NO at
        # (1 - ask). Net inventory = YES held - NO held; equal pairs are
        # riskless ($1 at resolution) so only the net matters for skew.
        inventory = (ctx.position_size(market.token_id_yes)
                     - ctx.position_size(market.token_id_no))
        if (abs(ref - self.last_quote_ref.get(token, -1)) <
                self.params["requote_tick"]
                and inventory == self.last_quote_inv.get(token)):
            return []

        sigma = math.sqrt(self.ewma_var.get(token, 0.0))
        half = max(self.params["min_spread"] / 2,
                   self.params["k_spread"] * sigma) * self.widen_mult[token]
        half = min(half, self.params["max_spread"] / 2)

        # inventory skew: shift the quote midpoint against current inventory
        skew = self.params["gamma"] * inventory * (1 + sigma * 100)
        center = ref - skew

        bid = max(0.001, min(0.998, center - half))
        ask = max(bid + 0.001, min(0.999, center + half))
        if ask - bid < self.params["min_spread"]:
            pad = (self.params["min_spread"] - (ask - bid)) / 2
            bid, ask = max(0.001, bid - pad), min(0.999, ask + pad)

        self.last_quote_ref[token] = ref
        self.last_quote_inv[token] = inventory

        size = self.params["quote_size"]
        reasoning = (f"mm ref={ref:.4f} sigma={sigma:.5f} half={half:.4f} "
                     f"inv={inventory:.0f} skew={skew:.4f} "
                     f"markout={avg_markout:.4f}x{len(self.markouts[token])}")
        max_inv = self.params["max_inventory"]
        intents = []
        if inventory < max_inv:  # may add YES exposure
            intents.append(Intent(
                strategy=self.name, token_id=market.token_id_yes,
                side=Side.BUY, price=bid, size=size, expected_edge=half,
                reasoning=reasoning, post_only=True,
                condition_id=market.condition_id, event_id=market.event_id))
        if inventory > -max_inv:  # may add NO exposure (synthetic YES ask)
            no_bid = max(0.001, min(0.998, 1.0 - ask))
            intents.append(Intent(
                strategy=self.name, token_id=market.token_id_no,
                side=Side.BUY, price=no_bid, size=size, expected_edge=half,
                reasoning=reasoning, post_only=True,
                condition_id=market.condition_id, event_id=market.event_id))
        return intents

    def _update_vol(self, token: str, ref: float) -> None:
        refs = self.refs[token]
        if refs:
            change = ref - refs[-1]
            lam = self.params["vol_lambda"]
            prev = self.ewma_var.get(token, change * change)
            self.ewma_var[token] = lam * prev + (1 - lam) * change * change
        refs.append(ref)
