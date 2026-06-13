"""
ResMap LOCAL control surface — kick off a data refresh from the browser instead
of the terminal. This is an operator tool, kept SEPARATE from the read-only
product API (tool/api/main.py) so that API stays purely read-only.

    uvicorn tool.api.control:app --port 8078     # localhost only

What "refresh" runs: ingest (pull all venues + detect rule changes) then export
(rebuild the Parquet snapshot) — exactly the daily scheduled job. It does NOT
run parse / equivalence: those cost Claude calls and depend on human review, so
they stay manual.

Auth: every endpoint except /health requires the X-Control-Token header to match
RESMAP_CONTROL_TOKEN (default 'resmap_local_control' for local use). This endpoint
executes a process — bind to localhost and set a real token before any exposure.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

CONTROL_TOKEN = os.environ.get("RESMAP_CONTROL_TOKEN") or "resmap_local_control"
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # apps/resmap


class Refresher:
    """Runs a sequence of named steps in a background thread; one run at a time.
    `status()` is safe to poll while it runs."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._last: dict | None = None
        self._log: list[str] = []
        self._started_at: float | None = None

    def status(self) -> dict:
        return {"running": self._running, "started_at": self._started_at,
                "last": self._last, "log": self._log[-60:]}

    def trigger(self, steps) -> bool:
        """Start a run; return False if one is already in flight."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._log = []
            self._started_at = time.time()
        threading.Thread(target=self._run, args=(steps,), daemon=True).start()
        return True

    def _run(self, steps) -> None:
        ok, results = True, []
        try:
            for name, fn in steps:
                self._log.append(f"▶ {name}")
                try:
                    out = fn()
                    self._log.append(f"✓ {name}: {out}")
                    results.append({"step": name, "ok": True})
                except Exception as exc:  # noqa: BLE001
                    self._log.append(f"✗ {name}: {exc}")
                    results.append({"step": name, "ok": False, "error": str(exc)})
                    ok = False
                    break
        finally:
            self._last = {"ok": ok, "results": results, "finished_at": time.time()}
            self._running = False


refresher = Refresher()


def _refresh_steps():
    """ingest then export, each as a subprocess using this venv's python."""
    def step(module: str):
        def run():
            # a full unbounded ingest of all venues + 70k+ upserts can run
            # 30-40 min; allow an hour (the job is async — nobody blocks on it)
            r = subprocess.run([sys.executable, "-m", module],
                               capture_output=True, text=True,
                               cwd=str(PROJECT_ROOT), timeout=3600)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout or "").strip()[-300:])
            lines = (r.stdout or "").strip().splitlines()
            return lines[-1] if lines else "ok"
        return run
    return [("ingest", step("ingest.run")), ("export", step("export.to_parquet"))]


app = FastAPI(title="ResMap Control", version="1.0.0",
              description="Local operator surface — trigger a data refresh.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def require_control(x_control_token: str = Header(default="")):
    if x_control_token != CONTROL_TOKEN:
        raise HTTPException(401, "invalid or missing X-Control-Token")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/status")
def status(_=Depends(require_control)):
    return refresher.status()


@app.post("/refresh")
def refresh(_=Depends(require_control)):
    if not refresher.trigger(_refresh_steps()):
        raise HTTPException(409, "a refresh is already running")
    return {"started": True}
