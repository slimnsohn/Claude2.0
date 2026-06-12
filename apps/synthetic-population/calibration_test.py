"""
Poll Calibration Regression Test
=================================
Creates polls matching real-world questions with known results,
runs CES-modeled auto-complete, and compares predicted vs actual.

Real data sources: Nate Silver aggregate, Reuters/Ipsos, Gallup, Pew, Morning Consult
Data as of March 2026.
"""

import json
import requests
import time

BASE = "http://localhost:5000"

# --- Benchmark polls with known real-world results ---
# Format: question text, expected yes%, expected no%, expected unsure%, source
BENCHMARKS = [
    {
        "question": "Do you approve of Trump's job performance?",
        "real": {"yes": 40.9, "no": 54.7, "unsure": 4.4},
        "source": "Nate Silver aggregate, March 2026",
    },
    {
        "question": "Do you approve of Trump's handling of tariffs on imported goods?",
        "real": {"yes": 34.0, "no": 64.0, "unsure": 2.0},
        "source": "Reuters/Ipsos, March 2026",
    },
    {
        "question": "Do you approve of US military strikes against Iran?",
        "real": {"yes": 27.0, "no": 43.0, "unsure": 30.0},
        "source": "Reuters/Ipsos, Feb-Mar 2026",
    },
    {
        "question": "Are you satisfied with the direction the country is going?",
        "real": {"yes": 24.0, "no": 74.0, "unsure": 2.0},
        "source": "Gallup, early 2026",
    },
    {
        "question": "Do you favor a strong military presence at the US-Mexico border?",
        "real": {"yes": 62.0, "no": 38.0, "unsure": 0.0},
        "source": "Pew Research, Feb 2026",
    },
    {
        "question": "Do you support suspending all applications for asylum?",
        "real": {"yes": 34.0, "no": 66.0, "unsure": 0.0},
        "source": "Pew Research, Feb 2026",
    },
    {
        "question": "Are current economic conditions in the country good?",
        "real": {"yes": 28.0, "no": 47.0, "unsure": 25.0},
        "source": "Gallup Economic Confidence, early 2026 (good vs poor, rest fair)",
    },
    {
        "question": "Do you think the economy is getting better?",
        "real": {"yes": 29.0, "no": 68.0, "unsure": 3.0},
        "source": "Gallup, early 2026 (better vs worse)",
    },
]


def create_and_run_poll(question: str) -> dict:
    """Create poll, auto-complete with CES model, return results."""
    # Create
    resp = requests.post(f"{BASE}/api/polls", json={"question": question}, timeout=15)
    if resp.status_code != 201:
        print(f"  ERROR creating poll: {resp.status_code} {resp.text[:200]}")
        return {}
    poll_id = resp.json()["poll_id"]

    # Auto-complete
    resp = requests.post(f"{BASE}/api/polls/{poll_id}/auto-complete", timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR auto-completing: {resp.status_code} {resp.text[:200]}")
        return {}

    data = resp.json()
    return {
        "poll_id": poll_id,
        "distribution": data.get("distribution", {}),
        "recorded": data.get("recorded", 0),
    }


def pct(val):
    return f"{val:5.1f}%"


def run_regression():
    print("=" * 80)
    print("POLL CALIBRATION REGRESSION TEST")
    print("CES-Modeled Population vs Real-World Polls")
    print("=" * 80)
    print()

    results = []

    for i, bench in enumerate(BENCHMARKS, 1):
        q = bench["question"]
        real = bench["real"]
        source = bench["source"]

        print(f"[{i}/{len(BENCHMARKS)}] {q}")
        print(f"  Source: {source}")

        result = create_and_run_poll(q)
        if not result:
            results.append(None)
            print()
            continue

        dist = result["distribution"]
        syn_yes = dist.get("yes", 0) * 100
        syn_no = dist.get("no", 0) * 100
        syn_unsure = dist.get("unsure", 0) * 100

        real_yes = real["yes"]
        real_no = real["no"]
        real_unsure = real["unsure"]

        err_yes = syn_yes - real_yes
        err_no = syn_no - real_no
        err_unsure = syn_unsure - real_unsure

        results.append({
            "question": q,
            "source": source,
            "predicted": {"yes": syn_yes, "no": syn_no, "unsure": syn_unsure},
            "real": real,
            "error": {"yes": err_yes, "no": err_no, "unsure": err_unsure},
            "abs_error_yes": abs(err_yes),
            "poll_id": result["poll_id"],
        })

        print(f"  Predicted:  yes={pct(syn_yes)}  no={pct(syn_no)}  unsure={pct(syn_unsure)}")
        print(f"  Real:       yes={pct(real_yes)}  no={pct(real_no)}  unsure={pct(real_unsure)}")
        print(f"  Error:      yes={err_yes:+5.1f}pp  no={err_no:+5.1f}pp  unsure={err_unsure:+5.1f}pp")
        print()

    # --- Scorecard ---
    valid = [r for r in results if r is not None]
    if not valid:
        print("No valid results to score.")
        return

    print("=" * 80)
    print("CALIBRATION SCORECARD")
    print("=" * 80)
    print()
    print(f"{'Question':<55} {'Pred':>8} {'Actual':>9} {'Error':>8}")
    print("-" * 80)

    total_abs_err = 0
    for r in valid:
        q_short = r["question"][:52] + "..." if len(r["question"]) > 55 else r["question"]
        syn_y = r["predicted"]["yes"]
        real_y = r["real"]["yes"]
        err_y = r["error"]["yes"]
        total_abs_err += r["abs_error_yes"]
        marker = " ***" if abs(err_y) > 10 else ""
        print(f"{q_short:<55} {pct(syn_y):>8} {pct(real_y):>9} {err_y:+6.1f}pp{marker}")

    mae = total_abs_err / len(valid)
    print("-" * 80)
    print(f"Mean Absolute Error (yes%): {mae:.1f} percentage points")
    print()

    if mae > 10:
        print("VERDICT: Population is significantly miscalibrated (MAE > 10pp)")
        print("Consider adding more real data sources or refining CES cross-tab matching")
    elif mae > 5:
        print("VERDICT: Moderate calibration gap (MAE 5-10pp)")
        print("Adding more real data sources or refining CES matching could close this")
    else:
        print("VERDICT: Reasonably calibrated (MAE < 5pp)")

    # Save full results
    out_path = "data/calibration_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "run_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "benchmarks": len(BENCHMARKS),
            "completed": len(valid),
            "mean_absolute_error_yes_pct": round(mae, 2),
            "results": valid,
        }, f, indent=2)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    run_regression()
