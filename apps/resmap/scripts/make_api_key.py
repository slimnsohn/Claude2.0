"""
Mint an API key for the read-only product surface. Generates a random key,
stores ONLY its hash in `api_keys`, and prints the raw key once — it cannot be
recovered later, so copy it now.

    python -m scripts.make_api_key --label "acme corp" --rate 120
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    from tool.api.auth import hash_key

    parser = argparse.ArgumentParser(description="mint a ResMap API key")
    parser.add_argument("--label", required=True, help="who/what the key is for")
    parser.add_argument("--rate", type=int, default=60, help="requests per minute")
    args = parser.parse_args(argv)

    raw = "rk_" + secrets.token_urlsafe(32)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (key_hash, label, rate_per_min) VALUES (%s,%s,%s)",
                (hash_key(raw), args.label, args.rate),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"label: {args.label}  rate: {args.rate}/min")
    print(f"API key (copy now — only the hash is stored, this is shown once):\n\n  {raw}\n")
    print("Use it as the X-API-Key header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
