"""Gamma API client — market/event metadata, fees, resolutions.

Field semantics confirmed by recon 2026-06-09 (scripts/recon.py):
- clobTokenIds: JSON string '["yes_id","no_id"]' (order matches outcomes)
- feeSchedule: {exponent, rate, takerOnly, rebateRate}; feesEnabled: bool
- markets have no category field -> derive from parent event tag slugs,
  falling back to feeType
- resolved markets: outcomePrices '["0","1"]' aligned with outcomes/token ids
"""
from __future__ import annotations

import json
from typing import Optional

import httpx
from pydantic import BaseModel

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Market
from pmtrader.datalayer.http_base import get_json

GAMMA_BASE = "https://gamma-api.polymarket.com"

KNOWN_CATEGORY_TAGS = [
    "geopolitics", "crypto", "sports", "politics", "economics",
    "culture", "tech", "finance", "weather", "world", "mentions",
]


class Event(BaseModel):
    id: str
    title: str
    neg_risk: bool = False
    end_date: Optional[str] = None
    markets: list[Market] = []


FEE_TYPE_CATEGORY_PREFIXES = [
    ("sports", "sports"), ("crypto", "crypto"), ("politic", "politics"),
    ("general", "general"), ("econ", "economics"),
]


def _category_from(raw: dict) -> str:
    # tags only exist on full /events payloads, not on events nested in /markets
    for ev in raw.get("events") or []:
        for tag in ev.get("tags") or []:
            slug = (tag.get("slug") or "").lower()
            if slug in KNOWN_CATEGORY_TAGS:
                return slug
    fee_type = (raw.get("feeType") or "").lower()
    for prefix, category in FEE_TYPE_CATEGORY_PREFIXES:
        if fee_type.startswith(prefix):
            return category
    return fee_type or "unknown"


def parse_market(raw: dict) -> Optional[Market]:
    try:
        token_ids = raw.get("clobTokenIds")
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
        if not token_ids or len(token_ids) < 2:
            return None
        fs = raw.get("feeSchedule")
        schedule = FeeSchedule(
            exponent=fs.get("exponent", 1.0), rate=fs["rate"],
            taker_only=fs.get("takerOnly", True), rebate_rate=fs.get("rebateRate", 0.0),
        ) if fs else None
        events = raw.get("events") or []
        return Market(
            condition_id=raw["conditionId"],
            question=raw.get("question", ""),
            category=_category_from(raw),
            token_id_yes=str(token_ids[0]),
            token_id_no=str(token_ids[1]),
            neg_risk=bool(raw.get("negRisk", False)),
            neg_risk_market_id=str(raw.get("negRiskMarketID") or ""),
            end_date=raw.get("endDate"),
            fee_schedule=schedule,
            fees_enabled=bool(raw.get("feesEnabled", True)),
            tick_size=float(raw.get("orderPriceMinTickSize") or 0.01),
            min_size=float(raw.get("orderMinSize") or 5.0),
            active=bool(raw.get("active", False)) and not bool(raw.get("closed", True)),
            volume_24h=float(raw.get("volume24hr") or 0.0),
            rewards_enabled=bool(raw.get("clobRewards")),
            event_id=str(events[0]["id"]) if events else None,
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def parse_resolution(raw: dict) -> Optional[tuple[Market, str]]:
    """Returns (market, winning_token_id) for a resolved market, else None."""
    market = parse_market(raw)
    if market is None:
        return None
    try:
        prices = raw.get("outcomePrices")
        if isinstance(prices, str):
            prices = json.loads(prices)
        prices = [float(p) for p in prices]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if len(prices) < 2 or sorted(prices) != [0.0, 1.0]:
        return None  # not a cleanly resolved binary (or 50/50 split resolution)
    winner = market.token_id_yes if prices[0] == 1.0 else market.token_id_no
    return market, winner


class GammaClient:
    def __init__(self, http: Optional[httpx.AsyncClient] = None,
                 base: str = GAMMA_BASE, retry_base_delay: float = 0.5):
        self.http = http or httpx.AsyncClient(timeout=30)
        self.base = base
        self.retry_base_delay = retry_base_delay

    async def close(self) -> None:
        await self.http.aclose()

    async def _paged(self, path: str, params: dict, page_size: int,
                     max_pages: int = 200) -> list[dict]:
        out: list[dict] = []
        for page in range(max_pages):
            page_params = {**params, "limit": page_size, "offset": page * page_size}
            batch = await get_json(self.http, f"{self.base}{path}", page_params,
                                   base_delay=self.retry_base_delay)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
        return out

    async def active_markets(self, page_size: int = 100) -> list[Market]:
        raws = await self._paged("/markets", {
            "active": "true", "closed": "false", "order": "volume24hr",
            "ascending": "false"}, page_size)
        return [m for m in (parse_market(r) for r in raws) if m is not None]

    async def resolved_markets(self, end_date_min: Optional[str] = None,
                               page_size: int = 100,
                               max_pages: int = 200) -> list[tuple[Market, str]]:
        params = {"closed": "true", "order": "endDate", "ascending": "false"}
        if end_date_min:
            params["end_date_min"] = end_date_min
        raws = await self._paged("/markets", params, page_size, max_pages)
        return [r for r in (parse_resolution(raw) for raw in raws) if r is not None]

    async def events(self, closed: bool = False, page_size: int = 50,
                     max_pages: int = 40) -> list[Event]:
        raws = await self._paged("/events", {
            "closed": str(closed).lower(), "order": "volume24hr",
            "ascending": "false"}, page_size, max_pages)
        out = []
        for raw in raws:
            markets = [m for m in (parse_market(r) for r in raw.get("markets", []))
                       if m is not None]
            out.append(Event(
                id=str(raw["id"]), title=raw.get("title", ""),
                neg_risk=bool(raw.get("negRisk", False)),
                end_date=raw.get("endDate"), markets=markets,
            ))
        return out
