"""
Current YES/NO prices for the divergence-play view. Polymarket + Kalshi only
(the equivalence layer is Poly<->Kalshi; Gemini is ingestion-only).

`extract_price` works on BOTH a live API response and a stored raw_payload —
the field names match per venue — so the API tries live first and falls back to
the last-ingested snapshot. Prices are 0..1 (a YES at 0.27 ≈ a 27% implied chance).
"""
from __future__ import annotations

import json
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


def live_price(venue_code: str, venue_market_id: str,
               timeout: float = 8.0) -> Optional[dict]:
    """Fetch the current price from the venue; None on any failure (caller
    falls back to the cached snapshot price)."""
    try:
        if venue_code == "polymarket":
            r = requests.get(f"{GAMMA}/markets",
                             params={"condition_ids": venue_market_id}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            m = data[0] if isinstance(data, list) and data else None
        elif venue_code == "kalshi":
            r = requests.get(f"{KALSHI}/markets/{venue_market_id}", timeout=timeout)
            r.raise_for_status()
            m = r.json().get("market")
        else:
            return None
        return extract_price(venue_code, m) if m else None
    except Exception:  # noqa: BLE001 — any failure → cached fallback
        return None
