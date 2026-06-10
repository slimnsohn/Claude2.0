"""Health check for the running trader. Exit 0 = healthy, 1 = dead/sick."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEARTBEAT = ROOT / "data" / "heartbeat"
DB = ROOT / "data" / "pmtrader.db"
DASHBOARD = "http://127.0.0.1:8765/api/state"

GREEN, RED, YELLOW, END = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
os.system("")  # enable ANSI colors in the Windows console

def ok(msg):   print(f"  {GREEN}OK{END}    {msg}")
def bad(msg):  print(f"  {RED}DEAD{END}  {msg}")
def warn(msg): print(f"  {YELLOW}WARN{END}  {msg}")


def main() -> int:
    healthy = True
    print(f"\npolymarket-trader status — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. heartbeat file (written by the trader every poll cycle)
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
        if age < 60:
            ok(f"heartbeat fresh ({age:.0f}s old)")
        else:
            bad(f"heartbeat stale ({age:.0f}s old) — trader is not looping")
            healthy = False
    except OSError:
        bad("no heartbeat file — trader has never run / data dir missing")
        healthy = False

    # 2. dashboard API
    try:
        with urllib.request.urlopen(DASHBOARD, timeout=5) as r:
            state = json.load(r)
        mode, halted = state["mode"], state["halted"]
        ok(f"dashboard up — mode={mode} equity=${state['equity']:.2f} "
           f"open_orders={len(state['open_orders'])} "
           f"positions={len(state['positions'])} markets={state['n_markets']}")
        if halted:
            warn(f"trading HALTED: {state.get('stop_reason')}")
    except Exception as exc:  # noqa: BLE001
        bad(f"dashboard unreachable ({type(exc).__name__}) — process likely dead")
        healthy = False

    # 3. recent activity in the DB (read-only; works even if API is down)
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        cur = con.cursor()
        now = time.time()
        snaps = cur.execute(
            "select count(*) from equity_snapshots where ts > ?",
            (now - 120,)).fetchone()[0]
        if snaps > 0:
            ok(f"equity snapshots flowing ({snaps} in last 2 min)")
        else:
            bad("no equity snapshots in 2 min — main loop is not running")
            healthy = False
        intents = cur.execute(
            "select count(*) from intents where ts > ?",
            (now - 3600,)).fetchone()[0]
        fills = cur.execute(
            "select count(*) from fills where ts > ?",
            (now - 86400,)).fetchone()[0]
        total_fills = cur.execute("select count(*) from fills").fetchone()[0]
        print(f"\n  activity: {intents} intents last hour · {fills} fills "
              f"last 24h · {total_fills} paper trades total (gate needs 200+ "
              f"per strategy)")
        con.close()
    except Exception as exc:  # noqa: BLE001
        warn(f"could not read DB: {type(exc).__name__}")

    print()
    if healthy:
        print(f"{GREEN}ALIVE{END} — dashboard: http://127.0.0.1:8765")
    else:
        print(f"{RED}NOT RUNNING{END} — restart with start.bat "
              "(or quick_starts\\polymarket-trader_start.bat)")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
