"""
Evaluation: heuristic ambulance dispatch vs. naive nearest-distance baseline.

Run from the backend/ folder with the virtual environment active:

    cd backend
    source .venv/bin/activate
    python scripts/eval_dispatch.py

Writes results to docs/dispatch_eval_results.csv and prints a summary
table to the console. Reproduces the "Ambulance Dispatch" section of
docs/evaluation_results.md.

Design note: each hospital normally has its own base ambulance(s) sitting
at distance 0, which trivially "wins" against every other candidate and
never exercises the heuristic's actual decision logic. To test the case
that matters -- choosing between ambulances at DIFFERENT hospitals when
the local one isn't free -- this script temporarily marks the origin
hospital's own base ambulances as unavailable for each scenario (and
restores them afterward), forcing a genuine cross-hospital comparison.

This does not modify your real dev data: all changes are rolled back
(db.rollback()) at the end of each scenario, never committed.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import AmbulanceModel, HospitalModel  # noqa: E402
from app.services.dispatch_service import DispatchService  # noqa: E402
from app.services.db_adapters import hospital_from_model  # noqa: E402

OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "dispatch_eval_results.csv"

SCENARIOS = [
    ("1", "critical"), ("2", "high"), ("3", "moderate"), ("4", "critical"),
    ("5", "high"), ("6", "moderate"), ("7", "critical"), ("8", "high"),
    ("9", "moderate"), ("1", "high"),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def main() -> None:
    service = DispatchService()
    rows = []

    with SessionLocal() as db:
        for origin_id, urgency in SCENARIOS:
            origin = db.get(HospitalModel, origin_id)
            if not origin:
                continue

            # Force a genuine cross-hospital decision: take the origin's own
            # base ambulances out of contention for this scenario only.
            local_ambulances = (
                db.query(AmbulanceModel)
                .filter(AmbulanceModel.base_hospital_id == origin_id, AmbulanceModel.status == "available")
                .all()
            )
            original_statuses = {a.id: a.status for a in local_ambulances}
            for a in local_ambulances:
                a.status = "transporting"  # temporarily remove from the available pool
            db.flush()

            try:
                available = db.query(AmbulanceModel).filter(AmbulanceModel.status == "available").all()
                if not available:
                    continue

                nearest8 = sorted(
                    available,
                    key=lambda a: haversine_km(a.latitude, a.longitude, origin.latitude, origin.longitude),
                )[:8]
                naive_pick = nearest8[0]

                origin_hospital = hospital_from_model(db, origin)
                traffic_prediction = service.traffic_model.predict(origin_hospital, origin_hospital)

                scored = sorted(
                    (
                        service._score_ambulance(db, amb, origin, urgency, traffic_prediction.congestion_ratio)
                        for amb in nearest8
                    ),
                    key=lambda r: r.score,
                )
                heuristic_pick = scored[0].ambulance
                naive_result = next(r for r in scored if r.ambulance.id == naive_pick.id)
                heuristic_result = scored[0]

                rows.append({
                    "origin": origin.name,
                    "urgency": urgency,
                    "naive_call_sign": naive_pick.call_sign,
                    "heuristic_call_sign": heuristic_pick.call_sign,
                    "differs": naive_pick.id != heuristic_pick.id,
                    "naive_distance_km": round(naive_result.distance_to_pickup_km, 2),
                    "heuristic_distance_km": round(heuristic_result.distance_to_pickup_km, 2),
                    "naive_coverage_penalty": round(naive_result.coverage_penalty, 3),
                    "heuristic_coverage_penalty": round(heuristic_result.coverage_penalty, 3),
                    "naive_pickup_risk": round(naive_result.pickup_risk_score, 3),
                    "heuristic_pickup_risk": round(heuristic_result.pickup_risk_score, 3),
                })
            finally:
                # Always restore original ambulance statuses, never commit.
                for a in local_ambulances:
                    a.status = original_statuses[a.id]
                db.rollback()

    if not rows:
        print("No dispatch scenarios produced — check that ambulances exist.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    differ_count = sum(1 for r in rows if r["differs"])
    print(f"Ran {len(rows)} dispatch scenarios (local base ambulances excluded), saved to {OUTPUT_PATH}")
    print(f"Heuristic differed from naive-nearest in {differ_count}/{len(rows)} cases\n")

    for r in rows:
        marker = " <-- DIFFERS" if r["differs"] else ""
        print(
            f"{r['origin'][:20]:20s} [{r['urgency']:8s}] "
            f"naive={r['naive_call_sign']:10s}({r['naive_distance_km']}km, risk={r['naive_pickup_risk']})  "
            f"heuristic={r['heuristic_call_sign']:10s}({r['heuristic_distance_km']}km, risk={r['heuristic_pickup_risk']}){marker}"
        )


if __name__ == "__main__":
    main()
