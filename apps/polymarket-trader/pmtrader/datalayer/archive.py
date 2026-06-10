"""Raw API response archive — every external payload kept, gzipped, for replay."""
from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path


class Archive:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def write(self, surface: str, payload, tag: str = "", ts: float | None = None) -> Path:
        ts = ts if ts is not None else time.time()
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        out = self.root / surface / day / f"{int(ts * 1000)}_{tag}.json.gz"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(gzip.compress(json.dumps(payload).encode()))
        return out

    def list(self, surface: str) -> list[Path]:
        base = self.root / surface
        if not base.exists():
            return []
        return sorted(base.rglob("*.json.gz"))

    @staticmethod
    def read(path: Path):
        return json.loads(gzip.decompress(path.read_bytes()))
