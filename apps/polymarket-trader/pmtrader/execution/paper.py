"""Paper execution: simulates fills against the real live order book.

Conservative by construction:
- Marketable orders fill by walking the displayed book (taker fees applied).
- Resting orders fill ONLY when a real trade prints strictly THROUGH the limit
  price, bounded by the print's size. A print at the limit price is not a fill
  (queue priority: others were ahead of us), and a touched quote is not a fill.
- Maker rebates are not credited.
Emits the same fill events and store writes as the live backend, so the rest
of the system cannot tell the difference.
"""
from __future__ import annotations

import itertools
import uuid
from typing import Callable

from pmtrader.core.fees import order_taker_fee
from pmtrader.core.models import (
    Fill, Intent, Market, OrderBook, OrderStatus, Position, Side,
)
from pmtrader.execution.state_machine import OrderRecord

_order_ids = itertools.count(1)


class PaperExecution:
    def __init__(self, store, starting_cash: float = 1000.0):
        self.store = store
        # run-scoped so order ids never collide with a previous run's DB rows
        self.run_id = uuid.uuid4().hex[:8]
        self.cash = starting_cash
        self.books: dict[str, OrderBook] = {}
        self.markets: dict[str, Market] = {}        # by condition_id
        self.token_market: dict[str, Market] = {}    # by token_id
        self.orders: dict[str, OrderRecord] = {}
        self._positions: dict[str, Position] = {}
        self.on_fill_callbacks: list[Callable[[Fill, OrderRecord], None]] = []

    # -- wiring -----------------------------------------------------------
    def register_market(self, market: Market) -> None:
        self.markets[market.condition_id] = market
        self.token_market[market.token_id_yes] = market
        self.token_market[market.token_id_no] = market

    def on_book(self, book: OrderBook) -> None:
        self.books[book.token_id] = book

    # -- queries ------------------------------------------------------------
    def open_orders(self) -> list[OrderRecord]:
        return [o for o in self.orders.values()
                if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)]

    def positions(self) -> dict[str, Position]:
        return {t: p for t, p in self._positions.items() if p.size > 1e-9}

    # -- order entry -----------------------------------------------------------
    def submit(self, intent: Intent, now: float) -> OrderRecord:
        rec = OrderRecord(order_id=f"paper-{self.run_id}-{next(_order_ids)}",
                          intent=intent, ts=now)
        self.orders[rec.order_id] = rec
        rec.transition(OrderStatus.SUBMITTED, now, "paper submit")
        book = self.books.get(intent.token_id)

        crosses = self._crosses(intent, book)
        if intent.post_only and crosses:
            rec.transition(OrderStatus.REJECTED, now, "post_only would cross")
            self._persist(rec)
            return rec

        if crosses:
            self._take(rec, book, now)
        if rec.status in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
            if rec.status == OrderStatus.SUBMITTED:
                rec.transition(OrderStatus.OPEN, now, "resting")
            # partially-filled remainder simply stays working
        self._persist(rec)
        return rec

    @staticmethod
    def _crosses(intent: Intent, book: OrderBook | None) -> bool:
        if book is None:
            return False
        if intent.side == Side.BUY:
            return book.best_ask is not None and intent.price >= book.best_ask
        return book.best_bid is not None and intent.price <= book.best_bid

    def _take(self, rec: OrderRecord, book: OrderBook, now: float) -> None:
        market = self.token_market.get(rec.intent.token_id)
        levels = (book._sorted_asks if rec.intent.side == Side.BUY
                  else book._sorted_bids)
        for level in levels:
            if rec.remaining <= 1e-9:
                break
            if rec.intent.side == Side.BUY and level.price > rec.intent.price:
                break
            if rec.intent.side == Side.SELL and level.price < rec.intent.price:
                break
            qty = min(rec.remaining, level.size)
            if qty <= 0:
                continue
            fee = order_taker_fee(level.price, qty,
                                  schedule=market.fee_schedule if market else None,
                                  fees_enabled=market.fees_enabled if market else True)
            self._fill(rec, level.price, qty, fee, maker=False, ts=now)

    # -- market data driving resting fills ------------------------------------------
    def on_trade(self, token_id: str, price: float, size: float, ts: float) -> None:
        for rec in self.open_orders():
            if rec.intent.token_id != token_id:
                continue
            i = rec.intent
            through = (i.side == Side.BUY and price < i.price) or \
                      (i.side == Side.SELL and price > i.price)
            if not through:
                continue
            qty = min(rec.remaining, size)
            if qty <= 0:
                continue
            self._fill(rec, i.price, qty, fee=0.0, maker=True, ts=ts)
            self._persist(rec)

    # -- cancels -------------------------------------------------------------------
    def cancel(self, order_id: str, now: float) -> None:
        rec = self.orders.get(order_id)
        if rec and rec.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
            rec.transition(OrderStatus.CANCELLED, now, "cancel")
            self._persist(rec)

    def cancel_all(self, now: float) -> None:
        for rec in self.open_orders():
            rec.transition(OrderStatus.CANCELLED, now, "cancel_all")
            self._persist(rec)

    # -- settlement -------------------------------------------------------------------
    def settle(self, condition_id: str, winning_token_id: str, ts: float) -> None:
        market = self.markets.get(condition_id)
        if market is None:
            return
        for token_id in (market.token_id_yes, market.token_id_no):
            pos = self._positions.pop(token_id, None)
            if pos and pos.size > 1e-9 and token_id == winning_token_id:
                self.cash += pos.size
        for rec in self.open_orders():
            if rec.intent.token_id in (market.token_id_yes, market.token_id_no):
                rec.transition(OrderStatus.EXPIRED, ts, "market resolved")
                self._persist(rec)

    # -- internals ------------------------------------------------------------------------
    def _fill(self, rec: OrderRecord, price: float, size: float, fee: float,
              maker: bool, ts: float) -> None:
        rec.apply_fill(size, price, ts)
        side = rec.intent.side
        notional = price * size
        self.cash += (-(notional + fee)) if side == Side.BUY else (notional - fee)

        pos = self._positions.get(rec.intent.token_id)
        if side == Side.BUY:
            if pos is None:
                pos = Position(token_id=rec.intent.token_id, size=0.0, avg_cost=0.0,
                               condition_id=rec.intent.condition_id,
                               event_id=rec.intent.event_id)
                self._positions[rec.intent.token_id] = pos
            total_cost = pos.avg_cost * pos.size + notional + fee
            pos.size += size
            pos.avg_cost = total_cost / pos.size
        elif pos is not None:
            pos.size -= size
            if pos.size <= 1e-9:
                self._positions.pop(rec.intent.token_id, None)

        fill = Fill(order_id=rec.order_id, token_id=rec.intent.token_id,
                    side=side, price=price, size=size, fee=fee, ts=ts, maker=maker)
        self.store.insert_fill(fill)
        for cb in self.on_fill_callbacks:
            cb(fill, rec)

    def _persist(self, rec: OrderRecord) -> None:
        from pmtrader.core.models import Order
        self.store.upsert_order(Order(
            id=rec.order_id, intent=rec.intent, status=rec.status,
            filled_size=rec.filled_size, avg_fill_price=rec.avg_fill_price,
            created_ts=rec.created_ts, updated_ts=rec.updated_ts))
