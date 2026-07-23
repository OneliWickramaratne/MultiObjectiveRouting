"""
Generate the capacity simulation chart.

Run AFTER eval_simulation.py (reads docs/simulation_eval_results.csv):

    cd backend
    python scripts/eval_simulation.py
    python scripts/generate_capacity_chart.py

Writes docs/capacity_simulation_chart.png.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = BACKEND_ROOT.parent / "docs" / "simulation_eval_results.csv"
OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "capacity_simulation_chart.png"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    if not CSV_PATH.exists():
        print(f"{CSV_PATH} not found — run eval_simulation.py first.")
        sys.exit(1)

    rows = list(csv.DictReader(open(CSV_PATH)))
    scenarios = [r["scenario_label"] for r in rows]
    transfers = [int(r["simulated_transfers"]) for r in rows]
    critical = [int(r["critical_transfers"]) for r in rows]
    amb_required = [int(r["ambulances_required"]) for r in rows]

    x = np.arange(len(scenarios))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width, transfers, width, label="Simulated transfers", color="#0ea894")
    ax.bar(x, critical, width, label="Critical transfers", color="#d6453d")
    ax.bar(x + width, amb_required, width, label="Ambulances required", color="#dc8a1f")
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace(" ", "\n") for s in scenarios])
    ax.set_ylabel("Count")
    ax.set_title("Capacity Simulation: Demand Across Network Stress Scenarios")
    ax.legend()
    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved chart to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
