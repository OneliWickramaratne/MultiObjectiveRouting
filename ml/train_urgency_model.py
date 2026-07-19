from __future__ import annotations

from pathlib import Path

try:
    import joblib
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing ML dependency. Install backend requirements first:\n"
        "  pip install -r backend/requirements.txt\n"
        f"Original error: {exc}"
    ) from exc


ARTIFACT_DIR = Path(__file__).parent / "artifacts"
DATA_PATH = ARTIFACT_DIR / "synthetic_transfer_data.csv"
MODEL_PATH = ARTIFACT_DIR / "urgency_model.joblib"
REPORT_PATH = ARTIFACT_DIR / "model_report.txt"


def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH} does not exist. Run generate_synthetic_transfer_data.py first."
        )
    return pd.read_csv(DATA_PATH)


def build_pipeline(model) -> Pipeline:
    categorical_features = [
        "condition_type",
        "oxygen_saturation_band",
        "blood_pressure_band",
        "consciousness_level",
        "required_icu_type",
        "age_band",
    ]
    boolean_features = ["ventilator_required"]
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
            ("bool", "passthrough", boolean_features),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    x = df.drop(columns=["urgency_class"])
    y = df["urgency_class"]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000),
        "random_forest": RandomForestClassifier(n_estimators=200, random_state=42),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),
    }

    reports: list[str] = []
    best_name = ""
    best_score = -1.0
    best_pipeline: Pipeline | None = None

    for name, model in candidates.items():
        pipeline = build_pipeline(model)
        pipeline.fit(x_train, y_train)
        score = pipeline.score(x_test, y_test)
        predictions = pipeline.predict(x_test)
        reports.append(f"MODEL: {name}\nAccuracy: {score:.4f}\n")
        reports.append(classification_report(y_test, predictions))
        reports.append("\n" + "=" * 72 + "\n")
        if score > best_score:
            best_name = name
            best_score = score
            best_pipeline = pipeline

    if best_pipeline is None:
        raise RuntimeError("No model was trained")

    joblib.dump(best_pipeline, MODEL_PATH)
    REPORT_PATH.write_text(
        f"Best model: {best_name}\nBest accuracy: {best_score:.4f}\n\n" + "\n".join(reports),
        encoding="utf-8",
    )
    print(f"Best model: {best_name} ({best_score:.4f})")
    print(f"Saved model to {MODEL_PATH}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
