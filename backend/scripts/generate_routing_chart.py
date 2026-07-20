"""
Generate the routing tradeoff chart from eval_routing.py's output.

Run this AFTER eval_routing.py (it reads docs/routing_eval_results.csv).

    cd backend
    source .venv/bin/activate
    pip install matplotlib --break-system-packages   # only needed once
    python scripts/eval_routing.py                    # produces the CSV
    python scripts/generate_routing_chart.py           # produces the chart

Writes docs/routing_tradeoff_chart.png.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = BACKEND_ROOT.parent / "docs" / "routing_eval_results.csv"
OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "routing_tradeoff_chart.png"

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("matplotlib/numpy not installed. Run:")
    print("  pip install matplotlib numpy --break-system-packages")
    sys.exit(1)


def main() -> None:
    if not CSV_PATH.exists():
        print(f"{CSV_PATH} not found — run eval_routing.py first.")
        sys.exit(1)

    rows = list(csv.DictReader(open(CSV_PATH)))
    by_urgency = defaultdict(list)
    for r in rows:
        by_urgency[r["urgency"]].append(r)

    urgencies = ["critical", "high", "moderate"]
    avg_time_delta = []
    pct_risk_reduction = []
    for urgency in urgencies:
        group = by_urgency[urgency]
        avg_td = sum(float(r["minutes_delta"]) for r in group) / len(group)
        avg_rd = sum(float(r["risk_delta"]) for r in group) / len(group)
        avg_shortest_risk = sum(float(r["shortest_risk"]) for r in group) / len(group)
        pct = -avg_rd / avg_shortest_risk * 100 if avg_shortest_risk else 0
        avg_time_delta.append(avg_td)
        pct_risk_reduction.append(pct)

    labels = [u.capitalize() for u in urgencies]
    x = np.arange(len(labels))
    width = 0.4

    fig, ax1 = plt.subplots(figsize=(8, 5.5))
    bars1 = ax1.bar(x - width / 2, avg_time_delta, width, label="Extra travel time (min)", color="#dc8a1f")
    ax1.set_ylabel("Avg. extra travel time (minutes)", color="#dc8a1f")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_xlabel("Patient urgency class")
    ax1.tick_params(axis="y", labelcolor="#dc8a1f")
    ax1.set_ylim(0, max(0.2, max(avg_time_delta) * 1.4))

    ax2 = ax1.twinx()
    bars2 = ax2.bar(x + width / 2, pct_risk_reduction, width, label="Road-risk reduction (%)", color="#279467")
    ax2.set_ylabel("Avg. road-risk reduction (%)", color="#279467")
    ax2.tick_params(axis="y", labelcolor="#279467")
    ax2.set_ylim(0, max(22, max(pct_risk_reduction) * 1.25))

    for bar, val in zip(bars1, avg_time_delta):
        ax1.text(bar.get_x() + bar.get_width() / 2, val + 0.004, f"{val:.3f}", ha="center", fontsize=9, color="#8a5a10")
    for bar, val in zip(bars2, pct_risk_reduction):
        ax2.text(bar.get_x() + bar.get_width() / 2, val + 0.4, f"{val:.1f}%", ha="center", fontsize=9, color="#1a5c40")

    plt.title(f"Urgency-Aware Routing: Time Cost vs. Risk Reduction\n(relative to shortest-time baseline, {len(rows)} route comparisons)", fontsize=11)
    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved chart to {OUTPUT_PATH}")

    print("\nValues used:")
    for label, td, rr in zip(labels, avg_time_delta, pct_risk_reduction):
        print(f"  {label:10s} avg_time_delta={td:+.3f} min  risk_reduction={rr:.1f}%")


if __name__ == "__main__":
    main()
