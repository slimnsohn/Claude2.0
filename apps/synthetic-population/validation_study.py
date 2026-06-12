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
    ("economy",     "Has your household income increased over the past year?"),
    ("immigration", "Do you support increasing border patrol on the US-Mexico border?"),
    ("immigration", "Do you support a pathway to citizenship for Dreamers brought to the US as children?"),
    ("immigration", "Do you support building a border wall?"),
    ("healthcare",  "Do you support repealing the Affordable Care Act?"),
    ("healthcare",  "Do you support Medicaid expansion?"),
    ("environment", "Do you support the EPA regulating carbon dioxide emissions?"),
    ("environment", "Do you support requiring renewable energy production?"),
    ("guns",        "Do you support banning assault rifles?"),
    ("guns",        "Do you support background checks on all gun sales?"),
    ("abortion",    "Do you support allowing abortion as a matter of choice?"),
    ("education",   "Do you support forgiving student loan debt?"),
    ("foreign_policy", "Do you support providing arms to Ukraine?"),
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
