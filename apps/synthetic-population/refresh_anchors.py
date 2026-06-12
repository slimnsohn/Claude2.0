"""Refresh calibration anchor real_results/date in data/benchmarks.json."""
import json
from pathlib import Path

FRESH = {
    "do you approve of trump's job performance?": {
        "real_results": {"yes": 0.40, "no": 0.57, "unsure": 0.03},
        "date": "2026-06-05",
        "source": "RealClearPolling aggregate",
    },
    "is the economy getting better or worse?": {
        "real_results": {"yes": 0.20, "no": 0.76, "unsure": 0.04},
        "date": "2026-05-17",
        "source": "Gallup Economic Confidence Index",
    },
}

p = Path("data/benchmarks.json")
benchmarks = json.loads(p.read_text())
seen = set()
for b in benchmarks:
    key = b.get("question", "").lower()
    if key in FRESH:
        b.update(FRESH[key])
        seen.add(key)
for key, vals in FRESH.items():
    if key not in seen:
        benchmarks.append({"question": key.capitalize(), **vals, "category": "anchor"})
p.write_text(json.dumps(benchmarks, indent=2))
print("Refreshed anchors:", sorted(seen) or "appended new entries")
