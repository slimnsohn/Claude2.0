"""Watchdog: stdlib-only supervisor for the trader process.

Starts `python -m pmtrader`, watches the heartbeat file, and restarts the
process if it crashes or the heartbeat goes stale (>60s). Max 5 restarts per
hour, then it stops and logs loudly — a process that keeps dying needs a
human, not a respawner. start.bat runs this, not the trader directly.
"""
from __future__ import annotations

import subprocess
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEARTBEAT = ROOT / "data" / "heartbeat"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
STALE_SECONDS = 60.0
MAX_RESTARTS_PER_HOUR = 5


def heartbeat_age() -> float:
    try:
        return time.time() - HEARTBEAT.stat().st_mtime
    except OSError:
        return float("inf")


def main() -> None:
    restarts: deque[float] = deque()
    while True:
        recent = [t for t in restarts if time.time() - t < 3600]
        if len(recent) >= MAX_RESTARTS_PER_HOUR:
            print(f"[watchdog] {len(recent)} restarts in the last hour — "
                  "giving up. Investigate before restarting.", flush=True)
            sys.exit(1)

        print("[watchdog] starting trader...", flush=True)
        proc = subprocess.Popen([str(PYTHON), "-m", "pmtrader"], cwd=str(ROOT))
        restarts.append(time.time())
        grace_until = time.time() + 120  # startup grace before staleness checks

        while True:
            code = proc.poll()
            if code is not None:
                if code == 0:
                    print("[watchdog] trader exited cleanly — done.", flush=True)
                    sys.exit(0)
                print(f"[watchdog] trader died (exit {code}); restarting",
                      flush=True)
                break
            if time.time() > grace_until and heartbeat_age() > STALE_SECONDS:
                print(f"[watchdog] heartbeat stale "
                      f"({heartbeat_age():.0f}s); killing trader", flush=True)
                proc.kill()
                proc.wait(timeout=30)
                break
            time.sleep(5)
        time.sleep(3)


if __name__ == "__main__":
    main()
