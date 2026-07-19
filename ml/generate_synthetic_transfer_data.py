from __future__ import annotations

import csv
import random
from pathlib import Path


OUTPUT_PATH = Path(__file__).parent / "artifacts" / "synthetic_transfer_data.csv"

CONDITIONS = ["respiratory", "cardiac", "trauma", "surgical", "neuro", "sepsis"]
OXYGEN = ["normal", "low", "critical"]
BP = ["stable", "unstable", "shock"]
CONSCIOUSNESS = ["alert", "reduced", "unconscious"]
ICU_TYPES = ["medical", "surgical", "cardiac", "trauma", "neuro", "pediatric"]


def calculate_label(row: dict[str, object]) -> str:
    score = 0.2
    if row["condition_type"] in {"respiratory", "cardiac", "trauma", "sepsis"}:
        score += 0.15
    if row["oxygen_saturation_band"] == "critical":
        score += 0.3
    elif row["oxygen_saturation_band"] == "low":
        score += 0.2
    if row["blood_pressure_band"] == "shock":
        score += 0.25
    elif row["blood_pressure_band"] == "unstable":
        score += 0.15
    if row["consciousness_level"] == "unconscious":
        score += 0.2
    elif row["consciousness_level"] == "reduced":
        score += 0.1
    if row["ventilator_required"]:
        score += 0.2
    if row["age_band"] == "elderly":
        score += 0.05

    score += random.uniform(-0.08, 0.08)
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "high"
    return "moderate"


def generate(rows: int = 1000) -> list[dict[str, object]]:
    random.seed(42)
    dataset = []
    for _ in range(rows):
        row: dict[str, object] = {
            "condition_type": random.choice(CONDITIONS),
            "oxygen_saturation_band": random.choices(OXYGEN, weights=[0.55, 0.30, 0.15])[0],
            "blood_pressure_band": random.choices(BP, weights=[0.60, 0.30, 0.10])[0],
            "consciousness_level": random.choices(CONSCIOUSNESS, weights=[0.65, 0.25, 0.10])[0],
            "ventilator_required": random.random() < 0.25,
            "required_icu_type": random.choice(ICU_TYPES),
            "age_band": random.choice(["child", "adult", "elderly"]),
        }
        row["urgency_class"] = calculate_label(row)
        dataset.append(row)
    return dataset


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = generate()
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
