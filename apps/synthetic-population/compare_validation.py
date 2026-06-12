"""Merge blind synthetic results with real poll numbers; compute deltas."""
import json

syn = json.load(open("data/validation_synthetic.json"))["results"]
real = {r["question"]: r for r in json.load(open("data/validation_real.json"))["results"]}

rows = []
for s in syn:
    r = real.get(s["question"])
    if not r:
        continue
    dy = s["synthetic"]["yes"] - r["real"]["yes"]
    mae = sum(abs(s["synthetic"][k] - r["real"][k]) for k in ("yes", "no", "unsure")) / 3
    rows.append({"q": s["question"], "col": s["ces_column"], "topic": s["topic"],
                 "syn": s["synthetic"], "real": r["real"], "delta_yes": round(dy, 3),
                 "mae": round(mae, 3), "source": r["source"], "date": r["date"],
                 "quality": r["quality"]})

rows.sort(key=lambda x: abs(x["delta_yes"]))
json.dump(rows, open("data/validation_report.json", "w"), indent=2)
for x in rows:
    print(f"{x['col']:12s} dYes={x['delta_yes']:+.3f} MAE={x['mae']:.3f} "
          f"[{x['quality']:6s}] {x['q'][:55]}")
