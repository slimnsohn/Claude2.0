"""Watchdog: stdlib-only supervisor for the trader process.

Starts `python -m pmtrader`, watches the heartbeat file, and restarts the
process if it crashes or the heartbeat goes stale (>60s). Max 5 restarts per
hour, then it stops and logs loudly — a process that keeps dying needs a
human, not a respawner. start.bat runs this, not the trader directly.
"""
from __future__ import annotations

import socket
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
LOCK_PORT = 8764  # mirrors pmtrader.core.lock (stdlib-only here on purpose)


def acquire_instance_lock() -> socket.socket | None:
    """Exclusive localhost bind held for the watchdog's lifetime; a second
    watchdog (double-clicked start.bat) must refuse to start, or two traders
    end up fighting over one DB, heartbeat file, and dashboard port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        sock.close()
        return None
    return sock


def heartbeat_age() -> float:
    try:
        return time.time() - HEARTBEAT.stat().st_mtime
    except OSError:
        return float("inf")


def main() -> None:
    lock = acquire_instance_lock()  # noqa: F841 — held until process exit
    if lock is None:
        print("[watchdog] another watchdog is already running — exiting. "
              "Check http://127.0.0.1:8765 or run status.bat.", flush=True)
        sys.exit(0)
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
