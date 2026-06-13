"""S4 calibration research: is Polymarket systematically miscalibrated anywhere?

Method (anti-spuriousness discipline):
- One observation per (resolved market, days-to-resolution band): the earliest
  YES price point in the band. Repeated points from one market are heavily
  autocorrelated and would inflate n, so they are NOT counted.
- Entry cost assumption: observed mid + half_spread (taker), plus the
  market's fee schedule at that price.
- Walk-forward: markets are split chronologically by resolution date into
  K folds; a bucket qualifies only if it shows positive net edge in EVERY
  fold AND the pooled Wilson lower bound clears price + fees + margin.
- Output: data/calibration_report.json (all buckets, qualified flag) and
  config/strategies/s4_whitelist.json (qualified buckets only).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmtrader.core.fees import taker_fee_per_share  # noqa: E402
from pmtrader.strategies.s4_calib import (  # noqa: E402
    Bucket, calibration_table, dtr_band, parse_end_date, wilson_lower,
)
from pmtrader.datalayer.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HALF_SPREAD = 0.01
MARGIN = 0.005
K_FOLDS = 3
MIN_N_POOLED = 100
MIN_N_FOLD = 20


def gather_observations(store: Store) -> list[dict]:
    """One obs per (market, band): (category, entry_price, days, won, resolved_ts)."""
    markets = {m.condition_id: m for m in store.all_markets()}
    obs = []
    for res in store.resolutions():
        m = markets.get(res["condition_id"])
        if m is None:
            continue
        end_ts = parse_end_date(m.end_date)
        if end_ts is None:
            continue
        history = store.price_history(m.token_id_yes)
        if not history:
            continue
        won = res["winning_token_id"] == m.token_id_yes
        seen_bands = set()
        for ts, price in history:
            days = (end_ts - ts) / 86400
            if days < 0:
                continue
            band = dtr_band(days)
            if band in seen_bands:
                continue
            seen_bands.add(band)
            # YES-side observation: buy YES at price + half spread
            entry = min(0.999, price + HALF_SPREAD)
            fee = taker_fee_per_share(entry, schedule=m.fee_schedule,
                                      fees_enabled=m.fees_enabled)
            obs.append({"category": m.category, "entry": entry, "days": days,
                        "won": won, "fee": fee, "end_ts": end_ts,
                        "condition_id": m.condition_id})
            # NO-side mirror: buy NO at (1 - price) + half spread. This is
            # how "the longshot is overpriced" becomes a tradeable bucket.
            no_entry = min(0.999, (1.0 - price) + HALF_SPREAD)
            no_fee = taker_fee_per_share(no_entry, schedule=m.fee_schedule,
                                         fees_enabled=m.fees_enabled)
            obs.append({"category": m.category, "entry": no_entry, "days": days,
                        "won": not won, "fee": no_fee, "end_ts": end_ts,
                        "condition_id": m.condition_id})
    return obs


def fold_of(i: int, n: int, k: int) -> int:
    return min(k - 1, i * k // n)


def main() -> None:
    store = Store(ROOT / "data" / "pmtrader.db")
    obs = gather_observations(store)
    store.close()
    print(f"observations: {len(obs)} from "
          f"{len({o['condition_id'] for o in obs})} resolved markets")
    if not obs:
        print("No data — run fetch_history first.")
        return

    obs.sort(key=lambda o: o["end_ts"])  # chronological for folds
    n = len(obs)

    pooled_rows = [(o["category"], o["entry"], o["days"], o["won"]) for o in obs]
    pooled = calibration_table(pooled_rows)

    # per-fold tables
    folds: list[list[dict]] = [[] for _ in range(K_FOLDS)]
    for i, o in enumerate(obs):
        folds[fold_of(i, n, K_FOLDS)].append(o)
    fold_tables = [calibration_table(
        [(o["category"], o["entry"], o["days"], o["won"]) for o in f]) for f in folds]

    report, whitelist = [], []
    for bucket, stats in sorted(pooled.items(), key=lambda kv: -kv[1].n):
        # representative entry price/fee for the bucket = decile midpoint
        mid_price = bucket.price_decile / 10 + 0.05
        bucket_obs = [o for o in obs
                      if min(9, int(o["entry"] * 10)) == bucket.price_decile
                      and o["category"] == bucket.category
                      and dtr_band(o["days"]) == bucket.dtr_band]
        avg_entry = sum(o["entry"] for o in bucket_obs) / len(bucket_obs)
        avg_fee = sum(o["fee"] for o in bucket_obs) / len(bucket_obs)
        pooled_edge = stats.wilson_lo - avg_entry - avg_fee

        fold_results = []
        for ft in fold_tables:
            fs = ft.get(bucket)
            if fs is None or fs.n < MIN_N_FOLD:
                fold_results.append(None)
            else:
                fold_results.append(fs.hit_rate - avg_entry - avg_fee)
        all_folds_positive = (all(r is not None and r > 0 for r in fold_results)
                              and len(fold_results) == K_FOLDS)
        qualified = (stats.n >= MIN_N_POOLED and pooled_edge > MARGIN
                     and all_folds_positive)
        row = {
            "category": bucket.category, "price_decile": bucket.price_decile,
            "dtr_band": bucket.dtr_band, "n": stats.n, "wins": stats.wins,
            "hit_rate": round(stats.hit_rate, 4),
            "wilson_lo": round(stats.wilson_lo, 4),
            "avg_entry": round(avg_entry, 4), "avg_fee": round(avg_fee, 5),
            "pooled_net_edge": round(pooled_edge, 4),
            "fold_net_edges": [None if r is None else round(r, 4) for r in fold_results],
            "qualified": qualified,
        }
        report.append(row)
        if qualified:
            whitelist.append({"category": bucket.category,
                              "price_decile": bucket.price_decile,
                              "dtr_band": bucket.dtr_band,
                              "wilson_lo": round(stats.wilson_lo, 4),
                              "n": stats.n})

    out = ROOT / "data" / "calibration_report.json"
    out.write_text(json.dumps({"n_observations": n, "k_folds": K_FOLDS,
                               "margin": MARGIN, "half_spread": HALF_SPREAD,
                               "buckets": report}, indent=2))
    wl_path = ROOT / "config" / "strategies" / "s4_whitelist.json"
    wl_path.parent.mkdir(parents=True, exist_ok=True)
    wl_path.write_text(json.dumps(whitelist, indent=2))

    print(f"\nreport -> {out}")
    print(f"whitelist -> {wl_path}  ({len(whitelist)} qualified buckets)")
    print("\nTop buckets by n:")
    for row in report[:15]:
        print(f"  {row['category']:>12} d{row['price_decile']} {row['dtr_band']:>6} "
              f"n={row['n']:>5} hit={row['hit_rate']:.3f} wl={row['wilson_lo']:.3f} "
              f"entry={row['avg_entry']:.3f} net={row['pooled_net_edge']:+.4f} "
              f"folds={row['fold_net_edges']} {'QUALIFIED' if row['qualified'] else ''}")


if __name__ == "__main__":
    main()
