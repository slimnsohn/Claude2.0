"""Kalshi API client with RSA-PSS signing auth."""

import json
import logging
import time
from pathlib import Path

import requests

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

import config

logger = logging.getLogger(__name__)


class KalshiClient:
    """Client for the Kalshi prediction market API with RSA-PSS auth."""

    def __init__(self, key_id: str = None, private_key_path: str = None):
        self.key_id = key_id or config.KALSHI_API_KEY
        self.base_url = config.KALSHI_BASE_URL
        self.delay = config.KALSHI_REQUEST_DELAY_S
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        # Load private key
        pk_path = private_key_path or config.KALSHI_PRIVATE_KEY_PATH
        self._private_key = None
        if self.key_id and pk_path:
            resolved = Path(pk_path)
            if not resolved.is_absolute():
                resolved = config.PROJECT_ROOT / pk_path
            if resolved.exists():
                if not HAS_CRYPTO:
                    raise ImportError(
                        "cryptography package required for Kalshi RSA auth. "
                        "Run: pip install cryptography"
                    )
                pem_data = resolved.read_bytes()
                self._private_key = serialization.load_pem_private_key(pem_data, password=None)
                logger.info("Kalshi RSA key loaded (key_id=%s...)", self.key_id[:8])
            else:
                logger.warning("Kalshi private key not found at %s", resolved)

    def _sign_request(self, method: str, path: str) -> dict:
        """Generate RSA-PSS signed auth headers for a Kalshi request.

        Matches the TypeScript reference implementation:
        payload = "{timestamp_ms}{METHOD}{path}" (no query params)
        Sign with RSA-PSS, SHA-256, MGF1(SHA-256), salt_length=32
        """
        if not self._private_key or not self.key_id:
            return {}

        import base64

        timestamp_ms = str(int(time.time() * 1000))
        # Strip query params from path for signing
        clean_path = path.split("?")[0]
        # Signature payload: {timestamp_ms}{METHOD}{path}
        payload = f"{timestamp_ms}{method.upper()}{clean_path}"

        # Sign the raw payload — the library hashes internally with SHA-256
        signature = self._private_key.sign(
            payload.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32,
            ),
            hashes.SHA256(),
        )

        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make a signed request with retry on 429 rate limits."""
        # Extract path for signing
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path

        auth_headers = self._sign_request(method, path)
        headers = kwargs.pop("headers", {})
        headers.update(auth_headers)

        max_retries = 3
        backoff = 2.0

        for attempt in range(max_retries + 1):
            # Re-sign on retry (timestamp changes)
            if attempt > 0:
                auth_headers = self._sign_request(method, path)
                headers.update(auth_headers)

            resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)

            if resp.status_code == 429:
                if attempt < max_retries:
                    wait = backoff * (2 ** attempt)
                    logger.warning("Rate limited (429). Retrying in %.1fs", wait)
                    time.sleep(wait)
                    continue
                logger.error("Rate limited after %d retries", max_retries)

            if resp.status_code >= 400:
                logger.error("Kalshi %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            return resp

        raise requests.exceptions.RetryError("Max retries exceeded on 429")

    @staticmethod
    def _normalize_market(raw: dict) -> dict:
        """Convert a raw Kalshi market dict to our normalized schema."""
        rules_primary = raw.get("rules_primary", "") or ""
        rules_secondary = raw.get("rules_secondary", "") or ""
        resolution_rules = "\n".join(filter(None, [rules_primary, rules_secondary]))

        # Kalshi API v2 uses _fp and _dollars suffixes — coerce to float
        def _num(val, default=0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        volume = _num(raw.get("volume_fp") or raw.get("volume") or raw.get("open_interest_fp"))
        liquidity = _num(raw.get("liquidity_dollars") or raw.get("liquidity"))
        yes_price = _num(raw.get("yes_ask_dollars") or raw.get("yes_ask") or raw.get("last_price_dollars"), None)

        return {
            "platform_id": raw.get("ticker", ""),
            "title": raw.get("title", ""),
            "resolution_rules": resolution_rules,
            "end_date": raw.get("expiration_time", ""),
            "volume": volume,
            "liquidity": liquidity,
            "current_yes_price": yes_price,
            "raw_json": raw,
        }

    # Kalshi ticker prefixes that indicate sports/parlay markets
    SPORTS_TICKER_PREFIXES = (
        "KXMLB", "KXNBA", "KXNFL", "KXNHL", "KXMVE", "KXNCAA",
        "KXUFC", "KXSOCCER", "KXTENNIS", "KXGOLF", "KXNASCAR",
        "KXWNBA", "KXMLS", "KXCFB", "KXCBB", "KXSPORT",
    )

    def _is_sports(self, raw: dict) -> bool:
        """Check if a raw Kalshi market is sports-related."""
        ticker = raw.get("ticker", "")
        event = raw.get("event_ticker", "")
        for prefix in self.SPORTS_TICKER_PREFIXES:
            if ticker.startswith(prefix) or event.startswith(prefix):
                return True
        return False

    def fetch_active_markets(self, min_volume: int = 10_000, limit: int = 100,
                             max_pages: int = 50, exclude_sports: bool = True) -> list[dict]:
        """Fetch active markets, optionally filtering out sports."""
        url = f"{self.base_url}/markets"
        cursor = None
        all_markets = []
        skipped_sports = 0
        page = 0

        while page < max_pages:
            params = {"market_status": "active", "limit": limit}
            if cursor:
                params["cursor"] = cursor

            try:
                resp = self._request("GET", url, params=params)
                data = resp.json()
            except requests.exceptions.RequestException:
                logger.exception("Failed to fetch Kalshi page %d", page + 1)
                break

            raw_markets = data.get("markets", [])
            for raw in raw_markets:
                if exclude_sports and self._is_sports(raw):
                    skipped_sports += 1
                    continue
                all_markets.append(self._normalize_market(raw))

            page += 1
            logger.info("Kalshi page %d: %d markets (total: %d)", page, len(raw_markets), len(all_markets))

            cursor = data.get("cursor")
            if not cursor or not raw_markets:
                break

            time.sleep(self.delay)

        if skipped_sports:
            logger.info("Kalshi: skipped %d sports markets", skipped_sports)

        filtered = [m for m in all_markets if m["volume"] >= min_volume]
        logger.info("Fetched %d Kalshi markets, %d passed min_volume=%d",
                     len(all_markets), len(filtered), min_volume)
        return filtered

    def fetch_resolved_markets(self, limit: int = 500) -> list[dict]:
        """Fetch resolved markets for backfill/audit."""
        url = f"{self.base_url}/markets"
        cursor = None
        all_markets = []

        while len(all_markets) < limit:
            params = {"market_status": "settled", "limit": min(100, limit - len(all_markets))}
            if cursor:
                params["cursor"] = cursor

            try:
                resp = self._request("GET", url, params=params)
                data = resp.json()
            except requests.exceptions.RequestException:
                logger.exception("Failed to fetch resolved markets")
                break

            raw_markets = data.get("markets", [])
            for raw in raw_markets:
                m = self._normalize_market(raw)
                m["outcome"] = raw.get("result", "UNKNOWN")
                m["resolved_at"] = raw.get("close_time", "")
                m["final_price"] = raw.get("last_price")
                all_markets.append(m)

            cursor = data.get("cursor")
            if not cursor or not raw_markets:
                break

            time.sleep(self.delay)

        logger.info("Fetched %d resolved Kalshi markets", len(all_markets))
        return all_markets

    def fetch_orderbook_depth(self, market_ticker: str) -> float | None:
        """Fetch orderbook and calculate total depth within 5% of midpoint."""
        url = f"{self.base_url}/markets/{market_ticker}/orderbook"

        try:
            resp = self._request("GET", url)
            data = resp.json()
        except requests.exceptions.RequestException:
            logger.exception("Failed to fetch orderbook for %s", market_ticker)
            return None

        orderbook = data.get("orderbook", data)
        yes_bids = orderbook.get("yes", []) or []
        no_bids = orderbook.get("no", []) or []

        all_orders = []
        for entry in yes_bids:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                all_orders.append((float(entry[0]), float(entry[1])))
        for entry in no_bids:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                all_orders.append((float(entry[0]), float(entry[1])))

        if not all_orders:
            return 0.0

        prices = [p for p, _ in all_orders]
        midpoint = (min(prices) + max(prices)) / 2.0
        if midpoint == 0:
            return 0.0

        threshold = 0.05 * midpoint
        depth = sum(qty for price, qty in all_orders
                    if abs(price - midpoint) <= threshold)

        return depth
