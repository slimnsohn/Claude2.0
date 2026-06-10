"""Record real WSS market-channel frames into a JSONL fixture for tests."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "wss_market_sample.jsonl"
DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0


async def main():
    r = httpx.get("https://gamma-api.polymarket.com/markets", params={
        "limit": 60, "active": "true", "closed": "false",
        "order": "volume24hr", "ascending": "false"}, timeout=30)
    markets = r.json()
    # prefer fast-churning crypto up/down markets for a lively fixture
    crypto = [m for m in markets if "up or down" in m.get("question", "").lower()
              or (m.get("feeType") or "").startswith("crypto")]
    chosen = (crypto or markets)[:10]
    print("recording:", [m["question"][:50] for m in chosen[:5]])
    tokens = []
    for m in chosen:
        ids = json.loads(m["clobTokenIds"]) if isinstance(m["clobTokenIds"], str) \
            else m["clobTokenIds"]
        tokens.extend(ids[:2])
    print(f"subscribing to {len(tokens)} tokens for {DURATION}s")

    frames = 0
    async with websockets.connect(
            "wss://ws-subscriptions-clob.polymarket.com/ws/market",
            open_timeout=15) as ws:
        await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
        loop = asyncio.get_event_loop()
        deadline = loop.time() + DURATION
        with OUT.open("w", encoding="utf-8") as f:
            while loop.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=deadline - loop.time())
                except (asyncio.TimeoutError, TimeoutError):
                    break
                f.write(msg.strip() + "\n")
                frames += 1
    print(f"recorded {frames} messages -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
