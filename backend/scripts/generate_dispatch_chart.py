"""
Generate the dispatch heuristic vs. naive-nearest chart.

Run AFTER eval_dispatch.py (reads docs/dispatch_eval_results.csv):

    cd backend
    python scripts/eval_dispatch.py
    python scripts/generate_dispatch_chart.py

Writes docs/dispatch_tradeoff_chart.png.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = BACKEND_ROOT.parent / "docs" / "dispatch_eval_results.csv"
OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "dispatch_tradeoff_chart.png"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    if not CSV_PATH.exists():
        print(f"{CSV_PATH} not found — run eval_dispatch.py first.")
        sys.exit(1)

    rows = list(csv.DictReader(open(CSV_PATH)))
    differing = [r for r in rows if r["differs"] == "True"]

    if not differing:
        print("No differing cases found in this run — nothing to chart.")
        sys.exit(0)

    cases = [r["origin"] for r in differing]
    dist_delta = [float(r["heuristic_distance_km"]) - float(r["naive_distance_km"]) for r in differing]
    risk_reduction = [
        -(float(r["heuristic_pickup_risk"]) - float(r["naive_pickup_risk"])) / float(r["naive_pickup_risk"]) * 100
        for r in differing
    ]

    x = np.arange(len(cases))
    width = 0.35
    fig, ax1 = plt.subplots(figsize=(7, 5))
    b1 = ax1.bar(x - width / 2, dist_delta, width, label="Distance delta (km)", color="#dc8a1f")
    ax1.set_ylabel("Distance delta (km)", color="#dc8a1f")
    ax1.axhline(0, color="#8b98a6", linewidth=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels([c.replace(" Hospital", "\nHospital") for c in cases])
    ax2 = ax1.twinx()
    b2 = ax2.bar(x + width / 2, risk_reduction, width, label="Pickup-risk reduction (%)", color="#279467")
    ax2.set_ylabel("Pickup-risk reduction (%)", color="#279467")
    ax1.set_title(f"Dispatch Heuristic vs. Naive-Nearest: The {len(differing)} Differing Case(s)")
    for bar, v in zip(b1, dist_delta):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + (0.03 if v >= 0 else -0.08), f"{v:+.2f}", ha="center", fontsize=9)
    for bar, v in zip(b2, risk_reduction):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + 1, f"{v:.1f}%", ha="center", fontsize=9)
    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved chart to {OUTPUT_PATH}")
    for c, d, r in zip(cases, dist_delta, risk_reduction):
        print(f"  {c}: distance_delta={d:+.2f}km  risk_reduction={r:.1f}%")


if __name__ == "__main__":
    main()
