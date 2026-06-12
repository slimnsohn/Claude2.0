"""Atomic registry read/write with rotating timestamped backups (keep 3)."""
import json
import os
from datetime import datetime
from pathlib import Path

MAX_BACKUPS = 3


def _registry_path(data_dir) -> Path:
    return Path(data_dir) / "profiles" / "registry.json"


def load_registry(data_dir) -> list:
    p = _registry_path(data_dir)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def save_registry(data_dir, profiles: list):
    p = _registry_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        p.replace(p.with_name(f"registry.backup.{ts}.json"))
        backups = sorted(p.parent.glob("registry.backup.*.json"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profiles, indent=2, default=str))
    os.replace(tmp, p)
