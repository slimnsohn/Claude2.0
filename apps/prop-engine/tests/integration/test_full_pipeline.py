"""End-to-end smoke test: dry-run pipeline against committed fixtures."""
import json
import shutil
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    app_copy = tmp_path / "prop-engine"
    shutil.copytree(
        ROOT, app_copy,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "data"),
    )
    (app_copy / "config" / "user.json").write_text(json.dumps({
        "bankroll": 10000,
        "min_edge_pct": 0.01,
        "kelly_fraction": 0.25,
        "max_stake_pct": 0.02,
        "min_bet_amount": 1.00,
        "books_to_consider": ["pinnacle", "fanduel", "bookmaker"],
    }))
    monkeypatch.chdir(app_copy)
    monkeypatch.syspath_prepend(str(app_copy))
    # Drop cached modules so the isolated copy is imported
    for mod in [m for m in list(sys.modules) if m.startswith(("core", "sports", "cli"))]:
        sys.modules.pop(mod, None)
    return app_copy


def test_full_pipeline_dry_run(isolated_app):
    import cli
    rc = cli.run_wnba(dry_run=True)
    assert rc == 0
    snapshot = isolated_app / "core" / "dashboard" / "static" / "data" / "today.json"
    assert snapshot.exists()
    data = json.loads(snapshot.read_text())
    assert "plays" in data
    assert "n_plays" in data
    assert isinstance(data["plays"], list)
