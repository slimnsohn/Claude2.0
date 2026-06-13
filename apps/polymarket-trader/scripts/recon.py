"""API recon — empirically verify every external assumption the system is built on.

Read-only, no auth required. Run before building (Phase 0) and any time
Polymarket changes something. Writes data/recon_findings.json.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import sys
import time
from pathlib import Path

import httpx
import websockets

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
WSS_MARKET = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
# Binance.com is geo-blocked (HTTP 451) from US IPs — Coinbase Exchange is the
# crypto spot source for this system.
COINBASE = "https://api.exchange.coinbase.com"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FINDINGS: dict = {"ran_at": time.time(), "probes": {}}


def record(name: str, ok: bool, detail: dict) -> None:
    FINDINGS["probes"][name] = {"ok": ok, **detail}
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    for k, v in detail.items():
        text = json.dumps(v) if not isinstance(v, str) else v
        print(f"        {k}: {text[:300]}")


def archive(tag: str, payload) -> None:
    out = DATA_DIR / "recon" / f"{int(time.time())}_{tag}.json.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(payload).encode()))


async def probe_gamma_markets(client: httpx.AsyncClient) -> dict | None:
    r = await client.get(f"{GAMMA}/markets", params={
        "limit": 5, "active": "true", "closed": "false", "order": "volumeNum", "ascending": "false"})
    r.raise_for_status()
    markets = r.json()
    archive("gamma_markets", markets)
    m = markets[0]
    fields = sorted(m.keys())
    needed = ["conditionId", "clobTokenIds", "endDate"]
    missing = [f for f in needed if f not in m]
    record("gamma_markets", not missing, {
        "n": len(markets), "missing_expected_fields": missing,
        "fee_like_fields": [f for f in fields if "fee" in f.lower()],
        "category_like_fields": [f for f in fields if f.lower() in
                                 ("category", "tags", "events") or "categ" in f.lower()],
        "negrisk_fields": [f for f in fields if "negrisk" in f.lower().replace("_", "")],
        "sample_fields": fields,
    })
    return m


async def probe_gamma_events(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{GAMMA}/events", params={"limit": 3, "closed": "false",
                                                    "order": "volume24hr", "ascending": "false"})
    r.raise_for_status()
    events = r.json()
    archive("gamma_events", events)
    e = events[0]
    record("gamma_events", "markets" in e, {
        "n": len(events),
        "has_nested_markets": "markets" in e,
        "negrisk_fields": [f for f in e.keys() if "negrisk" in f.lower().replace("_", "")],
        "sample_fields": sorted(e.keys()),
        "n_markets_in_first_event": len(e.get("markets", [])),
    })


def extract_token_ids(market: dict) -> list[str]:
    raw = market.get("clobTokenIds")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or []


async def probe_clob_book(client: httpx.AsyncClient, token_id: str) -> None:
    r = await client.get(f"{CLOB}/book", params={"token_id": token_id})
    r.raise_for_status()
    book = r.json()
    archive("clob_book", book)
    ok = "bids" in book and "asks" in book
    sample_level = (book.get("bids") or book.get("asks") or [{}])[0]
    record("clob_book", ok, {
        "fields": sorted(book.keys()),
        "level_fields": sorted(sample_level.keys()) if isinstance(sample_level, dict) else str(sample_level),
        "n_bids": len(book.get("bids", [])), "n_asks": len(book.get("asks", [])),
    })


async def probe_prices_history(client: httpx.AsyncClient, token_id: str) -> None:
    r = await client.get(f"{CLOB}/prices-history", params={
        "market": token_id, "interval": "max", "fidelity": 60})
    r.raise_for_status()
    hist = r.json().get("history", [])
    archive("clob_prices_history", hist[:100])
    ok = bool(hist) and "t" in hist[0] and "p" in hist[0]
    span_days = (hist[-1]["t"] - hist[0]["t"]) / 86400 if len(hist) > 1 else 0
    record("clob_prices_history", ok, {
        "n_points": len(hist), "span_days": round(span_days, 1),
        "point_format": hist[0] if hist else None,
        "first_ts": hist[0]["t"] if hist else None,
    })


async def probe_clob_market(client: httpx.AsyncClient, condition_id: str) -> None:
    r = await client.get(f"{CLOB}/markets/{condition_id}")
    r.raise_for_status()
    m = r.json()
    archive("clob_market", m)
    fee_fields = {k: m.get(k) for k in m.keys() if "fee" in k.lower()}
    record("clob_market", bool(m), {
        "fee_fields": fee_fields,
        "tick_size_fields": {k: m.get(k) for k in m.keys() if "tick" in k.lower()},
        "min_size_fields": {k: m.get(k) for k in m.keys() if "min" in k.lower()},
        "negrisk": {k: m.get(k) for k in m.keys() if "neg" in k.lower()},
        "fields": sorted(m.keys()),
    })


async def probe_resolved_market(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{GAMMA}/markets", params={
        "limit": 5, "closed": "true", "order": "endDate", "ascending": "false"})
    r.raise_for_status()
    markets = r.json()
    archive("gamma_resolved", markets)
    m = markets[0]
    outcome_fields = {k: m.get(k) for k in m.keys()
                      if "outcome" in k.lower() or "resolved" in k.lower() or "winner" in k.lower()}
    record("gamma_resolved", bool(outcome_fields), {
        "outcome_fields": outcome_fields,
        "umaResolutionStatus": m.get("umaResolutionStatus"),
    })


async def probe_coinbase(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{COINBASE}/products/BTC-USD/candles",
                         params={"granularity": 60})
    r.raise_for_status()
    candles = r.json()  # [[time, low, high, open, close, volume], ...] newest first
    record("coinbase_candles", len(candles) > 0 and len(candles[0]) == 6, {
        "n": len(candles), "candle_len": len(candles[0]),
        "sample_close": candles[0][4],
    })


async def probe_wss(token_id: str) -> None:
    try:
        async with websockets.connect(WSS_MARKET, open_timeout=15) as ws:
            await ws.send(json.dumps({"assets_ids": [token_id], "type": "market"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            frames = json.loads(msg)
            frame = frames[0] if isinstance(frames, list) else frames
            archive("wss_first_frame", frame)
            record("wss_market", True, {
                "event_type": frame.get("event_type"),
                "frame_fields": sorted(frame.keys()),
            })
    except Exception as exc:  # noqa: BLE001 — recon reports, doesn't crash
        record("wss_market", False, {"error": f"{type(exc).__name__}: {exc}"})


async def run_probe(name: str, coro) -> None:
    try:
        await coro
    except Exception as exc:  # noqa: BLE001 — recon reports, doesn't crash
        record(name, False, {"error": f"{type(exc).__name__}: {exc}"})


async def main() -> int:
    async with httpx.AsyncClient(timeout=30) as client:
        m = await probe_gamma_markets(client)
        if m is None:
            print("Cannot continue without a market sample.")
            return 1
        token_ids = extract_token_ids(m)
        condition_id = m.get("conditionId")
        await run_probe("gamma_events", probe_gamma_events(client))
        await run_probe("clob_book", probe_clob_book(client, token_ids[0]))
        await run_probe("clob_prices_history", probe_prices_history(client, token_ids[0]))
        await run_probe("clob_market", probe_clob_market(client, condition_id))
        await run_probe("gamma_resolved", probe_resolved_market(client))
        await run_probe("coinbase_candles", probe_coinbase(client))
    await probe_wss(token_ids[0])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "recon_findings.json").write_text(json.dumps(FINDINGS, indent=2))
    n_fail = sum(1 for p in FINDINGS["probes"].values() if not p["ok"])
    print(f"\n{len(FINDINGS['probes'])} probes, {n_fail} failures. "
          f"Findings -> {DATA_DIR / 'recon_findings.json'}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
