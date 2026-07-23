"""
Generate the urgency model comparison chart.

Run from the ml/ folder (same place as train_urgency_model.py):

    python generate_urgency_chart.py

This retrains all three models the same way train_urgency_model.py does
(same split, same random_state, so results match exactly) and plots
accuracy vs. critical-class recall. Writes urgency_model_chart.png.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ARTIFACT_DIR = Path(__file__).parent / "artifacts"
DATA_PATH = ARTIFACT_DIR / "synthetic_transfer_data.csv"
OUTPUT_PATH = ARTIFACT_DIR / "urgency_model_chart.png"


def build_pipeline(model) -> Pipeline:
    categorical_features = [
        "condition_type", "oxygen_saturation_band", "blood_pressure_band",
        "consciousness_level", "required_icu_type", "age_band",
    ]
    boolean_features = ["ventilator_required"]
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
            ("bool", "passthrough", boolean_features),
        ]
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    x = df.drop(columns=["urgency_class"])
    y = df["urgency_class"]
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42, stratify=y,
    )

    candidates = {
        "Logistic Regression": LogisticRegression(max_iter=1000),
        "Random Forest": RandomForestClassifier(n_estimators=200, random_state=42),
        "Gradient Boosting": GradientBoostingClassifier(random_state=42),
    }

    labels, accuracies, critical_recalls = [], [], []
    for name, model in candidates.items():
        pipeline = build_pipeline(model)
        pipeline.fit(x_train, y_train)
        accuracy = pipeline.score(x_test, y_test)
        predictions = pipeline.predict(x_test)
        report = classification_report(y_test, predictions, output_dict=True)
        critical_recall = report.get("critical", {}).get("recall", 0.0)

        labels.append(name)
        accuracies.append(accuracy * 100)
        critical_recalls.append(critical_recall * 100)
        print(f"{name}: accuracy={accuracy:.3f}  critical_recall={critical_recall:.3f}")

    x_pos = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7.5, 5))
    b1 = ax.bar(x_pos - width / 2, accuracies, width, label="Overall accuracy (%)", color="#0ea894")
    b2 = ax.bar(x_pos + width / 2, critical_recalls, width, label="Critical-class recall (%)", color="#d6453d")
    ax.set_ylabel("Percent")
    ax.set_xticks(x_pos)
    ax.set_xticklabels([l.replace(" ", "\n") for l in labels])
    ax.set_ylim(0, 100)
    ax.set_title("Urgency Classification Model Comparison")
    ax.legend(loc="lower right")
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 1, f"{h:.1f}", ha="center", fontsize=9)
    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150)
    print(f"\nSaved chart to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
