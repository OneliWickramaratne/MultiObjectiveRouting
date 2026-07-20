"""
Evaluation: capacity/fleet stress simulation across all four scenarios.

Run from the backend/ folder with the virtual environment active:

    cd backend
    source .venv/bin/activate
    python scripts/eval_simulation.py

Prints a summary table and writes docs/simulation_eval_results.csv.
Reproduces the "Capacity Simulation" section of docs/evaluation_results.md.

Note: this calls the same SimulationAnalyticsService used by the live
/api/admin/simulation/run endpoint — it is not a separate implementation,
so these are the exact numbers the running app would produce for the
same scenario/duration/intensity inputs.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services.capacity_forecast_service import CapacityForecastService  # noqa: E402
from app.services.simulation_analytics_service import SimulationAnalyticsService  # noqa: E402

OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "simulation_eval_results.csv"

SCENARIOS = ["baseline", "evening_surge", "mass_casualty", "respiratory_wave"]
DURATION_HOURS = 6
INTENSITY = 1.0


def main() -> None:
    capacity_forecast_service = CapacityForecastService()
    simulation_analytics_service = SimulationAnalyticsService()

    rows = []
    with SessionLocal() as db:
        forecasts = capacity_forecast_service.forecast_network(db)
        for scenario in SCENARIOS:
            result = simulation_analytics_service.run(
                db=db,
                forecasts=forecasts,
                scenario=scenario,
                duration_hours=DURATION_HOURS,
                intensity=INTENSITY,
            )
            rows.append(result)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario_label", "simulated_transfers", "critical_transfers",
        "ambulances_required", "ambulance_gap", "total_shortage_beds",
        "network_pressure_level",
    ]
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in fieldnames})

    print(f"Ran {len(rows)} scenarios, saved to {OUTPUT_PATH}\n")
    print(f"{'Scenario':18s} {'Transfers':10s} {'Critical':9s} {'Amb.Req':8s} {'Amb.Gap':8s} {'BedShortage':12s} {'NetworkPressure':16s}")
    for r in rows:
        print(
            f"{r['scenario_label']:18s} {r['simulated_transfers']:<10} {r['critical_transfers']:<9} "
            f"{r['ambulances_required']:<8} {r['ambulance_gap']:<8} {r['total_shortage_beds']:<12} "
            f"{r['network_pressure_level']:16s}"
        )


if __name__ == "__main__":
    main()
