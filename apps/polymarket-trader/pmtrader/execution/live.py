"""Live execution: signs real orders via py-clob-client.

Secret hygiene: this module NEVER logs order-client internals, exceptions are
logged by type+message only, and the private key is read from the environment
by the factory below — it never appears in any log record, config file, or
store row. Tests assert this.
"""
from __future__ import annotations

import itertools
import logging
import math
import os
from typing import Callable, Optional

from pmtrader.core.models import (
    Fill, Intent, Market, Order, OrderStatus, Side,
)
from pmtrader.execution.state_machine import OrderRecord

log = logging.getLogger(__name__)

_order_ids = itertools.count(1)


def make_clob_client():
    """Factory: builds an authenticated ClobClient from env vars.

    Required env vars (live mode only):
      POLYMARKET_PRIVATE_KEY, POLYMARKET_FUNDER_ADDRESS,
      POLYMARKET_SIGNATURE_TYPE (0 browser wallet, 1 email/Magic, 2 safe)
    """
    from py_clob_client.client import ClobClient

    key = os.environ.get("POLYMARKET_PRIVATE_KEY")
    funder = os.environ.get("POLYMARKET_FUNDER_ADDRESS")
    sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "1"))
    if not key or not funder:
        raise RuntimeError(
            "live mode requires POLYMARKET_PRIVATE_KEY and "
            "POLYMARKET_FUNDER_ADDRESS env vars")
    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137,
                        signature_type=sig_type, funder=funder)
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


class LiveExecution:
    def __init__(self, store, client):
        self.store = store
        self.client = client
        self.markets: dict[str, Market] = {}
        self.token_market: dict[str, Market] = {}
        self.orders: dict[str, OrderRecord] = {}
        self.on_fill_callbacks: list[Callable[[Fill, OrderRecord], None]] = []

    def register_market(self, market: Market) -> None:
        self.markets[market.condition_id] = market
        self.token_market[market.token_id_yes] = market
        self.token_market[market.token_id_no] = market

    def open_orders(self) -> list[OrderRecord]:
        return [o for o in self.orders.values()
                if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)]

    # -- order entry ---------------------------------------------------------
    def submit(self, intent: Intent, now: float) -> OrderRecord:
        from py_clob_client.clob_types import OrderArgs

        rec = OrderRecord(order_id=f"live-{next(_order_ids)}", intent=intent, ts=now)
        self.orders[rec.order_id] = rec
        market = self.token_market.get(intent.token_id)
        tick = market.tick_size if market else 0.01
        price = round(math.floor(intent.price / tick + 0.5) * tick, 6)
        size = float(int(intent.size))

        rec.transition(OrderStatus.SUBMITTED, now, "live submit")
        try:
            args = OrderArgs(token_id=intent.token_id, price=price, size=size,
                             side=intent.side.value)
            resp = self.client.create_and_post_order(args)
        except Exception as exc:  # noqa: BLE001 — exchange errors must not crash the loop
            rec.transition(OrderStatus.REJECTED, now,
                           f"api error: {type(exc).__name__}: {exc}")
            self._persist(rec)
            return rec

        if not resp or not resp.get("success"):
            why = (resp or {}).get("errorMsg", "no response")
            rec.transition(OrderStatus.REJECTED, now, f"exchange rejected: {why}")
        else:
            rec.exchange_id = resp.get("orderID")
            rec.transition(OrderStatus.OPEN, now, "exchange ack")
        self._persist(rec)
        return rec

    # -- fills arrive via the user WSS channel --------------------------------
    def on_user_fill(self, exchange_id: str, price: float, size: float,
                     fee: float, maker: bool, ts: float) -> None:
        rec = next((o for o in self.orders.values()
                    if o.exchange_id == exchange_id), None)
        if rec is None:
            log.warning("fill for unknown exchange order %s", exchange_id)
            return
        rec.apply_fill(size, price, ts)
        fill = Fill(order_id=rec.order_id, token_id=rec.intent.token_id,
                    side=rec.intent.side, price=price, size=size, fee=fee,
                    ts=ts, maker=maker)
        self.store.insert_fill(fill)
        self._persist(rec)
        for cb in self.on_fill_callbacks:
            cb(fill, rec)

    # -- cancels ----------------------------------------------------------------
    def cancel(self, order_id: str, now: float) -> None:
        rec = self.orders.get(order_id)
        if rec is None or rec.status not in (OrderStatus.OPEN,
                                             OrderStatus.PARTIALLY_FILLED):
            return
        try:
            if rec.exchange_id:
                self.client.cancel(rec.exchange_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("cancel failed for %s: %s", order_id, type(exc).__name__)
            return
        rec.transition(OrderStatus.CANCELLED, now, "cancel")
        self._persist(rec)

    def cancel_all(self, now: float = 0.0) -> None:
        try:
            self.client.cancel_all()
        except Exception as exc:  # noqa: BLE001
            log.error("cancel_all failed: %s", type(exc).__name__)
            return
        for rec in self.open_orders():
            rec.transition(OrderStatus.CANCELLED, now, "cancel_all")
            self._persist(rec)

    def close(self) -> None:
        self.cancel_all()

    # -- reconciliation after reconnect ---------------------------------------------
    def reconcile_with_api(self, api_orders: dict[str, dict], now: float) -> None:
        """api_orders: exchange_id -> {status, filled_size, avg_price}."""
        for rec in self.open_orders():
            if rec.exchange_id is None:
                continue
            api = api_orders.get(rec.exchange_id)
            if api is None:
                rec.reconcile("UNKNOWN", rec.filled_size, rec.avg_fill_price, now)
            else:
                rec.reconcile(api.get("status", "UNKNOWN"),
                              float(api.get("filled_size", 0.0)),
                              float(api.get("avg_price", 0.0)), now)
            self._persist(rec)

    def _persist(self, rec: OrderRecord) -> None:
        self.store.upsert_order(Order(
            id=rec.order_id, intent=rec.intent, status=rec.status,
            filled_size=rec.filled_size, avg_fill_price=rec.avg_fill_price,
            created_ts=rec.created_ts, updated_ts=rec.updated_ts,
            exchange_id=rec.exchange_id))
