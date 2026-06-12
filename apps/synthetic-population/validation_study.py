"""Multi-subject validation: poll the synthetic population on every CES-covered
subject and record distributions BEFORE looking up real-world numbers.

Usage: python validation_study.py
Writes: data/validation_synthetic.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

QUESTIONS = [
    ("approval",    "Do you approve of Trump's job performance?"),
    ("approval",    "Do you approve of the way Congress is handling its job?"),
    ("economy",     "Is the economy getting better or worse?"),
    ("economy",     "Are your personal finances better off than a year ago?"),
    ("immigration", "Do you support increasing border patrol on the US-Mexico border?"),
    ("immigration", "Do you support granting legal status to DREAMers brought to the US as children?"),
    ("immigration", "Do you support increasing deportation of undocumented immigrants?"),
    ("healthcare",  "Do you support repealing the Affordable Care Act?"),
    ("healthcare",  "Do you support Medicare for all?"),
    ("climate",     "Do you support a carbon tax on fossil fuels?"),
    ("climate",     "Do you support requiring renewable energy production?"),
    ("fiscal",      "Do you support raising taxes on income over $400k?"),
    ("fiscal",      "Do you support cutting federal spending by 5 percent?"),
    ("economy",     "Do you support raising the minimum wage to $15 per hour?"),
    ("education",   "Do you support forgiving student loan debt up to $50k?"),
]

RUNS = 10


def main():
    from server import create_app
    from engine.ces_columns import match_question

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    results = []
    for topic, q in QUESTIONS:
        col = match_question(q)
        if col is None:
            print(f"SKIP (no CES match): {q}")
            continue
        resp = client.post("/api/benchmarks/run", json={"question": q, "runs": RUNS})
        body = resp.get_json()
        if resp.status_code != 200 or "synthetic" not in body:
            print(f"ERROR {resp.status_code}: {q} -> {body}")
            continue
        row = {
            "topic": topic,
            "question": q,
            "ces_column": col["col_id"],
            "ces_name": col["name"],
            "synthetic": body["synthetic"],
            "runs": RUNS,
            "archetype_count": body.get("archetype_count"),
            "profile_count": body.get("profile_count"),
        }
        results.append(row)
        s = body["synthetic"]
        print(f"{col['col_id']:12s} yes={s['yes']:.3f} no={s['no']:.3f} "
              f"unsure={s['unsure']:.3f}  {q[:60]}")

    out = {
        "recorded_at": datetime.now().isoformat(),
        "protocol": "synthetic recorded BEFORE real numbers were looked up",
        "results": results,
    }
    Path("data/validation_synthetic.json").write_text(json.dumps(out, indent=2))
    print(f"\nSaved {len(results)} synthetic distributions to data/validation_synthetic.json")


if __name__ == "__main__":
    main()
