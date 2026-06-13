"""Polymarket API client for fetching active markets and orderbook data."""

import logging
import re
import time

import requests

from config import (
    POLYMARKET_BASE_URL,
    POLYMARKET_CLOB_URL,
    POLYMARKET_PAGE_DELAY_S,
)

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Client for the Polymarket Gamma and CLOB APIs (no auth required)."""

    def __init__(self) -> None:
        self.base_url = POLYMARKET_BASE_URL
        self.clob_url = POLYMARKET_CLOB_URL
        self.page_delay = POLYMARKET_PAGE_DELAY_S
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",  # avoid brotli decoding issues
        })

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    # Keywords in Polymarket titles/tags that indicate sports markets
    SPORTS_KEYWORDS = [
        " nfl ", " nba ", " mlb ", " nhl ", " ncaa ", " ufc ", " mma ",
        " wnba ", " mls ", " premier league", " la liga", " serie a",
        " bundesliga", " ligue 1", " champions league",
        "touchdown", "strikeout", "home run", "field goal",
        "rebounds", "assists", "3-pointers", "rushing yards",
        "passing yards", "receiving yards", "sacks",
        " parlay", "over/under", "spread",
        "grand slam", "match winner", "set winner",
    ]

    def _is_sports_poly(self, raw: dict) -> bool:
        """Check if a raw Polymarket market is sports-related."""
        title = (raw.get("question") or raw.get("title") or "").lower()
        # Check tags if available
        tags = " ".join(t.get("label", "") for t in raw.get("tags", [])).lower() if raw.get("tags") else ""
        combined = f" {title} {tags} "
        for kw in self.SPORTS_KEYWORDS:
            if kw in combined:
                return True
        return False

    def fetch_active_markets(
        self, min_volume: int = 10_000, limit: int = 100, max_pages: int = 60,
        exclude_sports: bool = True,
    ) -> list[dict]:
        """Fetch active markets from Polymarket.

        Paginates through the Gamma API (capped at max_pages),
        normalises each market, and filters by min_volume.
        """
        raw_markets: list[dict] = []
        offset = 0
        page = 0
        page_limit = min(limit, 100)  # API caps at 100

        while page < max_pages:
            params = {
                "active": "true",
                "closed": "false",
                "limit": page_limit,
                "offset": offset,
            }
            try:
                resp = self.session.get(
                    f"{self.base_url}/markets", params=params, timeout=30
                )
                resp.raise_for_status()
                page_data = resp.json()
            except requests.RequestException as exc:
                logger.warning(
                    "Polymarket request failed (offset=%d): %s", offset, exc,
                )
                break

            if not page_data:
                break

            raw_markets.extend(page_data)
            page += 1
            logger.info("Polymarket page %d/%d: %d markets (total: %d)",
                        page, max_pages, len(page_data), len(raw_markets))
            if len(page_data) < page_limit:
                break

            offset += page_limit
            time.sleep(self.page_delay)

        normalised = []
        skipped_sports = 0
        for m in raw_markets:
            if exclude_sports and self._is_sports_poly(m):
                skipped_sports += 1
                continue
            try:
                normalised.append(self._normalise_market(m))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to normalise market %s: %s",
                    m.get("id", "?"),
                    exc,
                )

        if skipped_sports:
            logger.info("Polymarket: skipped %d sports markets", skipped_sports)

        return [
            n
            for n in normalised
            if n["volume"] is not None and n["volume"] >= min_volume
        ]

    def fetch_orderbook_depth(self, token_id: str) -> float | None:
        """Return total liquidity within 5% of the midpoint for *token_id*.

        Uses the CLOB ``/book`` endpoint.  Returns ``None`` on any error.
        """
        try:
            resp = self.session.get(
                f"{self.clob_url}/book",
                params={"token_id": token_id},
                timeout=15,
            )
            resp.raise_for_status()
            book = resp.json()
        except requests.RequestException as exc:
            logger.warning(
                "Orderbook request failed for token %s: %s", token_id, exc
            )
            return None

        try:
            bids = book.get("bids", [])
            asks = book.get("asks", [])

            if not bids or not asks:
                return None

            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            mid = (best_bid + best_ask) / 2.0

            if mid == 0:
                return None

            depth = 0.0
            lower = mid * 0.95
            upper = mid * 1.05

            for level in bids:
                price = float(level["price"])
                if price >= lower:
                    depth += float(level["size"]) * price

            for level in asks:
                price = float(level["price"])
                if price <= upper:
                    depth += float(level["size"]) * price

            return depth
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning(
                "Orderbook depth calculation failed for token %s: %s",
                token_id,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalise_market(self, raw: dict) -> dict:
        """Convert a raw Gamma API market object to a standard dict."""
        yes_price = None

        # Method 1: outcomePrices array (current Gamma API format)
        outcomes = raw.get("outcomes", [])
        outcome_prices = raw.get("outcomePrices", [])
        if outcomes and outcome_prices:
            for outcome, price in zip(outcomes, outcome_prices):
                if outcome.upper() == "YES":
                    yes_price = _safe_float(price)
                    break

        # Method 2: tokens array (older format / some markets)
        if yes_price is None:
            tokens = raw.get("tokens", [])
            for token in tokens:
                outcome = (token.get("outcome") or "").upper()
                if outcome == "YES":
                    yes_price = _safe_float(token.get("price"))
                    break

        # Method 3: lastTradePrice as fallback
        if yes_price is None:
            yes_price = _safe_float(raw.get("lastTradePrice"))

        return {
            "platform_id": str(raw.get("id", raw.get("condition_id", ""))),
            "title": raw.get("question", ""),
            "resolution_rules": self._strip_html(raw.get("description", "")),
            "end_date": raw.get("end_date_iso"),
            "volume": _safe_float(raw.get("volume")),
            "liquidity": _safe_float(raw.get("liquidity")),
            "current_yes_price": yes_price,
            "raw_json": raw,
        }

    def _strip_html(self, text: str) -> str:
        """Strip HTML tags while preserving newlines and bullet structure."""
        if not text:
            return ""

        # Convert block-level elements to newlines
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</(?:p|div|h[1-6]|tr)>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
        text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode common HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")

        # Collapse excessive blank lines but preserve intentional structure
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _safe_float(value) -> float | None:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
