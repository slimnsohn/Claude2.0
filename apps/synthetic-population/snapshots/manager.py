import json
import copy
from pathlib import Path
from datetime import datetime


class SnapshotManager:
    """Manages immutable population snapshots for backtesting."""

    def __init__(self, snapshots_dir: Path, registry_path: Path):
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = Path(registry_path)
        self.manifest_path = self.snapshots_dir / "manifest.json"
        if not self.manifest_path.exists():
            self.manifest_path.write_text(json.dumps({"snapshots": []}))

    def _read_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text())

    def _write_manifest(self, manifest: dict):
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

    def create(self, date: str, label: str) -> str:
        slug = label.lower().replace(" ", "-")[:30]
        snap_id = f"SNAP-{date.replace('-', '')}-{slug}"
        profiles = json.loads(self.registry_path.read_text())
        event_dates = []
        for p in profiles:
            for entry in p.get("drift_log", []):
                d = entry.get("date", "")
                if d and d <= date:
                    event_dates.append(d)
        events_through = max(event_dates) if event_dates else None
        snap_file = self.snapshots_dir / f"{snap_id}.json"
        snap_file.write_text(json.dumps(profiles, indent=2, default=str))
        manifest = self._read_manifest()
        manifest["snapshots"].append({
            "snapshot_id": snap_id,
            "date": date,
            "label": label,
            "profile_count": len(profiles),
            "events_applied_through": events_through,
            "created_at": datetime.now().isoformat(),
            "file": f"{snap_id}.json",
        })
        self._write_manifest(manifest)
        return snap_id

    def load(self, snapshot_id: str, filter_drift_after: str = None) -> list[dict]:
        meta = self.get_metadata(snapshot_id)
        snap_file = self.snapshots_dir / meta["file"]
        profiles = json.loads(snap_file.read_text())
        if filter_drift_after:
            profiles = copy.deepcopy(profiles)
            for p in profiles:
                p["drift_log"] = [
                    entry for entry in p.get("drift_log", [])
                    if entry.get("date", "") <= filter_drift_after
                ]
        return profiles

    def list_snapshots(self) -> list[dict]:
        manifest = self._read_manifest()
        return manifest["snapshots"]

    def get_metadata(self, snapshot_id: str) -> dict:
        for snap in self.list_snapshots():
            if snap["snapshot_id"] == snapshot_id:
                return snap
        raise KeyError(f"Snapshot '{snapshot_id}' not found")

    def delete(self, snapshot_id: str):
        meta = self.get_metadata(snapshot_id)
        snap_file = self.snapshots_dir / meta["file"]
        if snap_file.exists():
            snap_file.unlink()
        manifest = self._read_manifest()
        manifest["snapshots"] = [
            s for s in manifest["snapshots"] if s["snapshot_id"] != snapshot_id
        ]
        self._write_manifest(manifest)
