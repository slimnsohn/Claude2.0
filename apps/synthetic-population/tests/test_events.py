import pytest
from monitor.events import EventStore


@pytest.fixture
def store(tmp_path):
    return EventStore(tmp_path / "events")


def test_add_event(store):
    event_id = store.add({
        "date": "2026-03-15",
        "description": "Supreme Court rules to restrict EPA authority",
        "affected_segments": {"party_id": {"republican": 0.1}},
    })
    assert event_id.startswith("EVT-")


def test_add_event_rejects_missing_fields(store):
    with pytest.raises(ValueError, match="Missing required field"):
        store.add({"description": "test"})


def test_get_event(store):
    event_id = store.add({
        "event_id": "EVT-TEST-001",
        "date": "2026-03-15",
        "description": "Test event",
        "affected_segments": {},
    })
    event = store.get(event_id)
    assert event["description"] == "Test event"


def test_get_nonexistent_raises(store):
    with pytest.raises(KeyError):
        store.get("EVT-NOPE")


def test_list_by_date_range(store):
    store.add({"event_id": "EVT-A", "date": "2026-03-10", "description": "A", "affected_segments": {}})
    store.add({"event_id": "EVT-B", "date": "2026-03-15", "description": "B", "affected_segments": {}})
    store.add({"event_id": "EVT-C", "date": "2026-03-20", "description": "C", "affected_segments": {}})
    events = store.list(start_date="2026-03-12", end_date="2026-03-18")
    assert len(events) == 1
    assert events[0]["event_id"] == "EVT-B"


def test_list_all(store):
    store.add({"event_id": "EVT-X", "date": "2026-01-01", "description": "X", "affected_segments": {}})
    store.add({"event_id": "EVT-Y", "date": "2026-12-31", "description": "Y", "affected_segments": {}})
    events = store.list()
    assert len(events) == 2
