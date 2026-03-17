import json
from pathlib import Path
from datetime import datetime


class EventStore:
    """Manages event ingestion and storage."""

    def __init__(self, events_dir: Path):
        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def add(self, event: dict) -> str:
        """Validate, assign event_id, save to events_dir/{event_id}.json. Returns event_id."""
        for field in ("date", "description", "affected_segments"):
            if field not in event:
                raise ValueError(f"Missing required field: {field}")

        event_id = event.get("event_id", f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        event["event_id"] = event_id

        path = self.events_dir / f"{event_id}.json"
        path.write_text(json.dumps(event, indent=2))
        return event_id

    def get(self, event_id: str) -> dict:
        """Return single event by ID."""
        path = self.events_dir / f"{event_id}.json"
        if not path.exists():
            raise KeyError(f"Event '{event_id}' not found")
        return json.loads(path.read_text())

    def list(self, start_date: str = None, end_date: str = None) -> list[dict]:
        """Return events in date range (inclusive). Dates as 'YYYY-MM-DD' strings."""
        events = []
        for path in sorted(self.events_dir.glob("*.json")):
            event = json.loads(path.read_text())
            if start_date and event.get("date", "") < start_date:
                continue
            if end_date and event.get("date", "") > end_date:
                continue
            events.append(event)
        return events
