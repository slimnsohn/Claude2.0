"""Replay engine: drives the real strategy classes over stored price history.

Honesty limits (by design, documented in the spec):
- Sampled mids, not real books -> books are synthesized with a conservative
  assumed half-spread and effectively infinite depth. Microstructure
  strategies (S2) cannot be judged here; this harness is for S1/S3/S4-class
  logic and produces *pessimistic-cost* results.
- Maker fills require a later tick strictly through the order price
  (touch != fill). Maker rebates are ignored.
- Settlement uses the stored resolution; if its timestamp predates the last
  tick it settles just after the final tick instead.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pmtrader.backtest.costs import CostModel
from pmtrader.backtest.stats import bootstrap_ci, max_drawdown
from pmtrader.core.models import Intent, Level, Market, OrderBook, Position, Side
from pmtrader.datalayer.store import Store
from pmtrader.strategies.base import Strategy, StrategyContext

DEEP = 1_000_000.0  # synthetic book depth


@dataclass
class Lot:
    strategy: str
    token_id: str
    size: float
    cost: float  # total cash spent including fees/slippage (positive number)
    entry_ts: float


@dataclass
class ClosedTrade:
    strategy: str
    token_id: str
    size: float
    pnl: float
    entry_ts: float
    exit_ts: float


@dataclass
class RestingOrder:
    intent: Intent
    placed_ts: float


@dataclass
class BacktestResult:
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[tuple[float, float]] = field(default_factory=list)
    final_equity: float = 0.0
    starting_cash: float = 0.0

    @property
    def per_trade_pnl(self) -> list[float]:
        return [t.pnl for t in self.trades]

    def per_strategy_pnl(self) -> dict[str, list[float]]:
        out: dict[str, list[float]] = defaultdict(list)
        for t in self.trades:
            out[t.strategy].append(t.pnl)
        return dict(out)

    def summary(self) -> dict:
        pnl = self.per_trade_pnl
        lo, hi = bootstrap_ci(pnl)
        return {
            "n_trades": len(pnl),
            "total_pnl": sum(pnl),
            "mean_pnl": sum(pnl) / len(pnl) if pnl else 0.0,
            "ci95": (lo, hi),
            "max_drawdown": max_drawdown([e for _, e in self.equity_curve]),
            "final_equity": self.final_equity,
            "return_pct": (self.final_equity / self.starting_cash - 1) * 100
                          if self.starting_cash else 0.0,
        }


class ReplayEngine:
    def __init__(self, store: Store, strategies: list[Strategy], cost: CostModel,
                 start_ts: float = 0.0, end_ts: float = float("inf"),
                 starting_cash: float = 1000.0):
        self.store = store
        self.strategies = strategies
        self.cost = cost
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.cash = starting_cash
        self.starting_cash = starting_cash
        self.lots: list[Lot] = []
        self.resting: list[RestingOrder] = []
        self.marks: dict[str, float] = {}  # token_id -> latest mid
        self.result = BacktestResult(starting_cash=starting_cash)

    # -- data prep -----------------------------------------------------------
    def _load(self):
        markets = {m.condition_id: m for m in self.store.all_markets()}
        resolutions = {r["condition_id"]: r for r in self.store.resolutions()}
        ticks: list[tuple[float, str]] = []  # (ts, condition_id)
        series: dict[str, dict[float, float]] = {}
        last_tick: dict[str, float] = {}
        for cid, m in markets.items():
            ys = dict(self.store.price_history(m.token_id_yes, self.start_ts, self.end_ts))
            ns = dict(self.store.price_history(m.token_id_no, self.start_ts, self.end_ts))
            if not ys:
                continue
            series[m.token_id_yes] = ys
            series[m.token_id_no] = ns
            for ts in ys:
                ticks.append((ts, cid))
                last_tick[cid] = max(last_tick.get(cid, 0.0), ts)
        ticks.sort(key=lambda t: (t[0], t[1]))
        return markets, resolutions, series, ticks, last_tick

    def _book(self, token_id: str, mid: float, ts: float) -> OrderBook:
        bid = max(0.001, mid - self.cost.half_spread)
        ask = min(0.999, mid + self.cost.half_spread)
        return OrderBook(token_id=token_id, ts=ts,
                         bids=[Level(price=bid, size=DEEP)],
                         asks=[Level(price=ask, size=DEEP)])

    def _positions(self) -> dict[str, Position]:
        agg: dict[str, list[Lot]] = defaultdict(list)
        for lot in self.lots:
            agg[lot.token_id].append(lot)
        out = {}
        for token_id, lots in agg.items():
            size = sum(l.size for l in lots)
            cost = sum(l.cost for l in lots)
            out[token_id] = Position(token_id=token_id, size=size,
                                     avg_cost=cost / size if size else 0.0)
        return out

    def _equity(self) -> float:
        return self.cash + sum(lot.size * self.marks.get(lot.token_id, lot.cost / lot.size)
                               for lot in self.lots)

    # -- fills ----------------------------------------------------------------
    def _fill_taker(self, market: Market, intent: Intent, mid: float, ts: float) -> None:
        price = self.cost.synthetic_quote(mid, intent.side)
        if intent.side == Side.BUY and intent.price < price:
            self.resting.append(RestingOrder(intent, ts))  # limit below market: rests
            return
        if intent.side == Side.SELL and intent.price > price:
            self.resting.append(RestingOrder(intent, ts))
            return
        cash_delta, _fee = self.cost.taker_fill_cost(market, intent.side, price, intent.size)
        self._apply_fill(market, intent, price, cash_delta, ts)

    def _fill_maker(self, market: Market, intent: Intent, ts: float) -> None:
        cash_delta, _fee = self.cost.maker_fill_cost(market, intent.side,
                                                     intent.price, intent.size)
        self._apply_fill(market, intent, intent.price, cash_delta, ts)

    def _apply_fill(self, market: Market, intent: Intent, price: float,
                    cash_delta: float, ts: float) -> None:
        self.cash += cash_delta
        if intent.side == Side.BUY:
            self.lots.append(Lot(intent.strategy, intent.token_id, intent.size,
                                 -cash_delta, ts))
        else:
            self._close_lots(intent.strategy, intent.token_id, intent.size,
                             cash_delta, ts)

    def _close_lots(self, strategy: str, token_id: str, size: float,
                    proceeds: float, ts: float) -> None:
        remaining = size
        for lot in [l for l in self.lots
                    if l.token_id == token_id and l.strategy == strategy]:
            if remaining <= 0:
                break
            take = min(lot.size, remaining)
            frac = take / lot.size
            lot_cost = lot.cost * frac
            lot_proceeds = proceeds * (take / size)
            self.result.trades.append(ClosedTrade(
                strategy, token_id, take, lot_proceeds - lot_cost, lot.entry_ts, ts))
            lot.size -= take
            lot.cost -= lot_cost
            remaining -= take
        self.lots = [l for l in self.lots if l.size > 1e-12]

    def _check_resting(self, market: Market, ts: float) -> None:
        still = []
        for ro in self.resting:
            i = ro.intent
            if i.token_id not in (market.token_id_yes, market.token_id_no):
                still.append(ro)
                continue
            mid = self.marks.get(i.token_id)
            if mid is None or ts <= ro.placed_ts:
                still.append(ro)
                continue
            if i.side == Side.BUY and mid < i.price:      # strict trade-through
                self._fill_maker(market, i, ts)
            elif i.side == Side.SELL and mid > i.price:
                self._fill_maker(market, i, ts)
            else:
                still.append(ro)
        self.resting = still

    # -- settlement ------------------------------------------------------------
    def _settle(self, market: Market, winner: str, ts: float) -> None:
        for lot in [l for l in self.lots if l.token_id in
                    (market.token_id_yes, market.token_id_no)]:
            payout = lot.size * (1.0 if lot.token_id == winner else 0.0)
            self.cash += payout
            self.result.trades.append(ClosedTrade(
                lot.strategy, lot.token_id, lot.size, payout - lot.cost,
                lot.entry_ts, ts))
        self.lots = [l for l in self.lots if l.token_id not in
                     (market.token_id_yes, market.token_id_no)]
        self.resting = [ro for ro in self.resting if ro.intent.token_id not in
                        (market.token_id_yes, market.token_id_no)]
        self.marks[market.token_id_yes] = 1.0 if winner == market.token_id_yes else 0.0
        self.marks[market.token_id_no] = 1.0 if winner == market.token_id_no else 0.0

    # -- main loop ---------------------------------------------------------------
    def run(self) -> BacktestResult:
        markets, resolutions, series, ticks, last_tick = self._load()
        for ts, cid in ticks:
            market = markets[cid]
            yes_mid = series[market.token_id_yes].get(ts)
            no_mid = series[market.token_id_no].get(ts)
            if no_mid is None and yes_mid is not None:
                no_mid = 1.0 - yes_mid
            self.marks[market.token_id_yes] = yes_mid
            self.marks[market.token_id_no] = no_mid

            self._check_resting(market, ts)

            books = {market.token_id_yes: self._book(market.token_id_yes, yes_mid, ts),
                     market.token_id_no: self._book(market.token_id_no, no_mid, ts)}
            ctx = StrategyContext(now=ts, cash=self.cash, budget=self.cash,
                                  positions=self._positions())
            for strategy in self.strategies:
                for intent in strategy.on_books(market, books, ctx):
                    mid = yes_mid if intent.token_id == market.token_id_yes else no_mid
                    if intent.post_only:
                        self.resting.append(RestingOrder(intent, ts))
                    else:
                        self._fill_taker(market, intent, mid, ts)
            self.result.equity_curve.append((ts, self._equity()))

        # settle resolved markets after their final tick
        settlements = []
        for cid, res in resolutions.items():
            if cid not in markets or cid not in last_tick:
                continue
            ts = res["resolved_ts"]
            if ts <= last_tick[cid]:
                ts = last_tick[cid] + 1.0
            settlements.append((ts, cid, res["winning_token_id"]))
        for ts, cid, winner in sorted(settlements):
            self._settle(markets[cid], winner, ts)
            self.result.equity_curve.append((ts, self._equity()))

        self.result.final_equity = self._equity()
        return self.result
