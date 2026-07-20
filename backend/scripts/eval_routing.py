"""
Evaluation: shortest-time vs. urgency-aware risk-routing.

Run from the backend/ folder with the virtual environment active:

    cd backend
    source .venv/bin/activate
    python scripts/eval_routing.py

Writes results to docs/routing_eval_results.csv and prints a summary
table to the console. Reproduces the "Routing Evaluation" section of
docs/evaluation_results.md.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.data_store import get_hospital  # noqa: E402
from app.services.routing_service import RoutingService  # noqa: E402

OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "routing_eval_results.csv"

# A spread of real origin-destination pairs across the network.
PAIRS = [
    ("1", "2"),
    ("1", "9"),
    ("4", "7"),
    ("6", "8"),
    ("2", "5"),
    ("9", "1"),
    ("7", "6"),
    ("8", "2"),
]
URGENCIES = ["critical", "high", "moderate"]


def main() -> None:
    service = RoutingService()
    rows = []

    for origin_id, dest_id in PAIRS:
        origin = get_hospital(origin_id)
        dest = get_hospital(dest_id)
        for urgency in URGENCIES:
            routes = service.compare_routes(origin, dest, urgency)
            by_strategy = {r.strategy: r for r in routes}
            shortest = by_strategy.get("shortest_time")
            risk_aware = by_strategy.get("ml_traffic_risk_aware")
            if not shortest or not risk_aware:
                continue
            rows.append({
                "origin": origin.name,
                "destination": dest.name,
                "urgency": urgency,
                "shortest_minutes": round(shortest.estimated_minutes, 2),
                "shortest_risk": round(shortest.risk_score, 3) if shortest.risk_score is not None else None,
                "aware_minutes": round(risk_aware.estimated_minutes, 2),
                "aware_risk": round(risk_aware.risk_score, 3) if risk_aware.risk_score is not None else None,
                "minutes_delta": round(risk_aware.estimated_minutes - shortest.estimated_minutes, 2),
                "risk_delta": round((risk_aware.risk_score or 0) - (shortest.risk_score or 0), 3),
            })

    if not rows:
        print("No route comparisons produced — check OSM graph / hospital IDs.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Ran {len(rows)} route comparisons, saved to {OUTPUT_PATH}\n")
    for r in rows:
        print(
            f"{r['origin'][:20]:20s} -> {r['destination'][:20]:20s} [{r['urgency']:8s}] "
            f"shortest={r['shortest_minutes']:.1f}min/risk={r['shortest_risk']}  "
            f"aware={r['aware_minutes']:.1f}min/risk={r['aware_risk']}  "
            f"delta_time={r['minutes_delta']:+.1f}min delta_risk={r['risk_delta']:+.3f}"
        )

    print("\nAggregate by urgency:")
    by_urgency = defaultdict(list)
    for r in rows:
        by_urgency[r["urgency"]].append(r)
    for urgency in ["critical", "high", "moderate"]:
        group = by_urgency[urgency]
        if not group:
            continue
        avg_time_delta = sum(r["minutes_delta"] for r in group) / len(group)
        avg_risk_delta = sum(r["risk_delta"] for r in group) / len(group)
        avg_shortest_risk = sum(r["shortest_risk"] for r in group) / len(group)
        pct_risk_reduction = -avg_risk_delta / avg_shortest_risk * 100 if avg_shortest_risk else 0
        print(f"  {urgency:10s} avg_delta_time={avg_time_delta:+.3f} min  avg_risk_reduction={pct_risk_reduction:.1f}%")


if __name__ == "__main__":
    main()
