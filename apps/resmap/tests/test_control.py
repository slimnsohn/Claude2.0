"""Tests for the local control server (refresh trigger)."""
import threading
import time

import pytest

import tool.api.control as control
from tool.api.control import Refresher


# ── Refresher state machine (unit, no subprocesses) ──────────────────────────

def test_run_executes_steps_in_order():
    r = Refresher()
    calls = []
    r._run([("a", lambda: calls.append("a") or "A"),
            ("b", lambda: calls.append("b") or "B")])
    assert calls == ["a", "b"]
    st = r.status()
    assert st["running"] is False
    assert st["last"]["ok"] is True


def test_run_stops_on_first_failure():
    r = Refresher()
    ran = []

    def boom():
        raise RuntimeError("kaboom")

    r._run([("a", lambda: ran.append("a")), ("bad", boom),
            ("c", lambda: ran.append("c"))])
    assert ran == ["a"]                       # c never ran
    assert r.status()["last"]["ok"] is False


def test_trigger_rejects_when_already_running():
    r = Refresher()
    r._running = True
    assert r.trigger([("a", lambda: "A")]) is False


def test_trigger_runs_async_then_returns_to_idle():
    r = Refresher()
    assert r.trigger([("a", lambda: (time.sleep(0.01), "A")[1])]) is True
    for _ in range(300):
        if not r.status()["running"]:
            break
        time.sleep(0.01)
    assert r.status()["running"] is False
    assert r.status()["last"]["ok"] is True


# ── endpoints (TestClient) ───────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(control, "CONTROL_TOKEN", "testtoken")
    control.refresher = Refresher()          # fresh state per test
    monkeypatch.setattr(control, "_refresh_steps",
                        lambda: [("noop", lambda: "done")])
    return TestClient(control.app)


T = {"X-Control-Token": "testtoken"}


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"ok": True}


def test_status_requires_token(client):
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers=T).status_code == 200


def test_refresh_requires_token(client):
    assert client.post("/refresh").status_code == 401


def test_refresh_starts_and_completes(client):
    assert client.post("/refresh", headers=T).json() == {"started": True}
    for _ in range(300):
        st = client.get("/status", headers=T).json()
        if not st["running"]:
            break
        time.sleep(0.01)
    assert st["running"] is False
    assert st["last"]["ok"] is True


def test_refresh_conflict_when_running(client):
    control.refresher._running = True        # pretend a run is in flight
    assert client.post("/refresh", headers=T).status_code == 409
