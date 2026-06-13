"""
Current YES/NO prices for the divergence-play view. Polymarket + Kalshi only
(the equivalence layer is Poly<->Kalshi; Gemini is ingestion-only).

`extract_price` works on BOTH a live API response and a stored raw_payload —
the field names match per venue — so the API tries live first and falls back to
the last-ingested snapshot. Prices are 0..1 (a YES at 0.27 ≈ a 27% implied chance).
Fees (both venues charge ONLY on the trade, never at settlement — sources:
help.polymarket.com/en/articles/13364478-trading-fees and the Kalshi fee schedule):
  - Polymarket taker = price · rate · (price·(1−price))^exponent per share, with
    rate/exponent from the market's own feeSchedule (maker orders pay 0). Fee-free
    if feesEnabled is false.
  - Kalshi taker = 0.07 · price · (1−price) per contract, rounded up to 1¢.
"""
from __future__ import annotations

import json
import math
from typing import Optional

import requests

GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _loads(x):
    """outcomes/outcomePrices arrive as JSON strings or already-parsed lists."""
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            return json.loads(x)
        except json.JSONDecodeError:
            return None
    return None


def extract_price(venue_code: str, m: dict) -> Optional[dict]:
    """Return {'yes': float, 'no': float} in [0,1], or None if unavailable."""
    if not m:
        return None

    if venue_code == "polymarket":
        yes = no = None
        outs, prices = _loads(m.get("outcomes")), _loads(m.get("outcomePrices"))
        if outs and prices and len(outs) == len(prices):
            for o, p in zip(outs, prices):
                if str(o).lower() == "yes":
                    yes = _f(p)
                elif str(o).lower() == "no":
                    no = _f(p)
        if yes is None:
            bb, ba = _f(m.get("bestBid")), _f(m.get("bestAsk"))
            if bb is not None and ba is not None:
                yes = round((bb + ba) / 2, 4)
            elif _f(m.get("lastTradePrice")) is not None:
                yes = _f(m.get("lastTradePrice"))
        if yes is None:
            return None
        if no is None:
            no = round(1 - yes, 4)
        return {"yes": yes, "no": no}

    if venue_code == "kalshi":
        yb, ya = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
        if yb is not None and ya is not None:
            yes = round((yb + ya) / 2, 4)
        else:
            yes = _f(m.get("last_price_dollars"))
        if yes is None:
            return None
        return {"yes": yes, "no": round(1 - yes, 4)}

    return None  # gemini etc. not priced (not in the equivalence layer)


def extract_fees(venue_code: str, m: Optional[dict],
                 yes: float, no: float) -> dict:
    """Estimated TAKER fee to BUY YES at `yes` and to BUY NO at `no` (per
    contract/share). Both venues charge fees only on the trade — $0 at
    settlement — so a fee only raises your entry cost."""
    if venue_code == "kalshi":
        def kf(p):
            return math.ceil(0.07 * p * (1 - p) * 100) / 100   # round up to 1¢
        return {"yes_fee": kf(yes), "no_fee": kf(no),
                "fee_model": "Kalshi taker 7%·p·(1−p)/contract, rounded up to 1¢; $0 at settlement"}

    if venue_code == "polymarket":
        if not m or not m.get("feesEnabled"):
            return {"yes_fee": 0.0, "no_fee": 0.0, "fee_model": "Polymarket: fee-free market"}
        fs = m.get("feeSchedule") or {}
        rate, exp = _f(fs.get("rate")), _f(fs.get("exponent"))
        if rate is None:
            return {"yes_fee": 0.0, "no_fee": 0.0, "fee_model": "Polymarket: no fee schedule"}
        exp = 1.0 if exp is None else exp

        def pf(p):
            return round(p * rate * ((p * (1 - p)) ** exp), 4)
        return {"yes_fee": pf(yes), "no_fee": pf(no),
                "fee_model": f"Polymarket taker {rate:g}·p·(p(1−p))^{exp:g}/share "
                             f"(maker 0); $0 at settlement"}

    return {"yes_fee": 0.0, "no_fee": 0.0, "fee_model": "no fee model"}


def live_market(venue_code: str, venue_market_id: str,
                timeout: float = 8.0) -> Optional[dict]:
    """Fetch the current market object from the venue (carries price AND fee
    schedule); None on any failure so the caller falls back to the snapshot."""
    try:
        if venue_code == "polymarket":
            r = requests.get(f"{GAMMA}/markets",
                             params={"condition_ids": venue_market_id}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data[0] if isinstance(data, list) and data else None
        if venue_code == "kalshi":
            r = requests.get(f"{KALSHI}/markets/{venue_market_id}", timeout=timeout)
            r.raise_for_status()
            return r.json().get("market")
        return None
    except Exception:  # noqa: BLE001 — any failure → cached fallback
        return None
