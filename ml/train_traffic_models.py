from __future__ import annotations

import argparse
import shutil
from pathlib import Path

try:
    import joblib
    import pandas as pd
    from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing ML dependency. Install backend requirements first:\n"
        "  pip install -r backend/requirements.txt\n"
        f"Original error: {exc}"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = PROJECT_ROOT / "ml" / "artifacts"
DATA_CANDIDATES = [
    PROJECT_ROOT / "data" / "traffic_model_ready.csv",
    PROJECT_ROOT / "_incoming_hos_zip" / "HOS" / "traffic_model_ready.csv",
]

FEATURES = [
    "pair_id",
    "origin_hospital_id",
    "destination_hospital_id",
    "hour",
    "minute",
    "dayofweek_num",
    "is_weekend",
    "is_morning_peak",
    "is_evening_peak",
    "is_night",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "distanceMeters",
    "distance_km",
    "static_duration_seconds",
    "osm_intersection_count",
    "osm_signal_count",
    "osm_route_risk_score",
    "traffic_normal_interval_count",
    "traffic_slow_interval_count",
    "traffic_jam_interval_count",
    "road_mix_trunk",
    "road_mix_primary",
    "road_mix_secondary",
    "road_mix_tertiary_local",
    "intersections_per_km",
    "signals_per_km",
    "jam_interval_ratio",
    "slow_or_jam_ratio",
    "static_eta_over_distance",
    "hospital_pair_code",
    "traffic_band_code",
]

TRAINING_PROFILES = {
    "compact": {
        "random_forest": {"n_estimators": 80, "max_depth": 16, "min_samples_leaf": 3},
        "extra_trees": {"n_estimators": 80, "max_depth": 16, "min_samples_leaf": 3},
        "gradient_boosting": {"n_estimators": 160, "max_depth": 3},
        "compress": 3,
        "minimum_free_gb": 1.0,
    },
    "balanced": {
        "random_forest": {"n_estimators": 220, "max_depth": 24, "min_samples_leaf": 2},
        "extra_trees": {"n_estimators": 220, "max_depth": 24, "min_samples_leaf": 2},
        "gradient_boosting": {"n_estimators": 260, "max_depth": 3},
        "compress": 3,
        "minimum_free_gb": 3.0,
    },
    "research": {
        "random_forest": {"n_estimators": 400, "max_depth": None, "min_samples_leaf": 1},
        "extra_trees": {"n_estimators": 400, "max_depth": None, "min_samples_leaf": 1},
        "gradient_boosting": {"n_estimators": 400, "max_depth": 3},
        "compress": 3,
        "minimum_free_gb": 8.0,
    },
}


def find_data_path() -> Path:
    for path in DATA_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(
        "No traffic_model_ready.csv found. Put it in data/traffic_model_ready.csv "
        "or keep the imported _incoming_hos_zip/HOS folder."
    )


def evaluate_model(name: str, model, x_train, x_test, y_train, y_test) -> tuple[str, object, float]:
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    mae = mean_absolute_error(y_test, predictions)
    rmse = mean_squared_error(y_test, predictions) ** 0.5
    r2 = r2_score(y_test, predictions)
    report = f"{name}: MAE={mae:.4f}, RMSE={rmse:.4f}, R2={r2:.4f}"
    return report, model, mae


def train_target(df: pd.DataFrame, target: str, output_name: str, profile: dict) -> list[str]:
    x = df[FEATURES].fillna(0)
    y = df[target]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
    )
    candidates = {
        "random_forest": RandomForestRegressor(
            **profile["random_forest"],
            random_state=42,
            n_jobs=-1,
        ),
        "extra_trees": ExtraTreesRegressor(
            **profile["extra_trees"],
            random_state=42,
            n_jobs=-1,
        ),
        "gradient_boosting": GradientBoostingRegressor(
            **profile["gradient_boosting"],
            random_state=42,
        ),
    }

    reports: list[str] = [f"Target: {target}"]
    best_name = ""
    best_model = None
    best_mae = float("inf")
    for name, model in candidates.items():
        report, fitted_model, mae = evaluate_model(name, model, x_train, x_test, y_train, y_test)
        reports.append(report)
        if mae < best_mae:
            best_name = name
            best_model = fitted_model
            best_mae = mae

    if best_model is None:
        raise RuntimeError(f"No model trained for {target}")

    output_path = ARTIFACT_DIR / output_name
    joblib.dump(best_model, output_path, compress=profile["compress"])
    reports.append(f"Best: {best_name}")
    reports.append(f"Saved: {output_path}")
    reports.append("")
    return reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=sorted(TRAINING_PROFILES),
        default="balanced",
        help="Training strength. Use research only when there is plenty of free disk/RAM.",
    )
    parser.add_argument(
        "--skip-space-check",
        action="store_true",
        help="Train even if free-space detection reports less than the profile minimum.",
    )
    return parser.parse_args()


def ensure_free_space(profile: dict, skip_space_check: bool) -> str:
    usage = shutil.disk_usage(ARTIFACT_DIR.parent)
    free_gb = usage.free / (1024**3)
    required_gb = float(profile["minimum_free_gb"])
    message = f"Free disk space: {free_gb:.2f} GB. Required for profile: {required_gb:.2f} GB."
    if free_gb < required_gb and not skip_space_check:
        raise SystemExit(
            message
            + "\nFree more space or rerun with --profile compact. "
            + "Use --skip-space-check only if the OS reading is known to be wrong."
        )
    return message


def main() -> None:
    args = parse_args()
    profile = TRAINING_PROFILES[args.profile]
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    space_message = ensure_free_space(profile, args.skip_space_check)
    data_path = find_data_path()
    df = pd.read_csv(data_path)
    required = set(FEATURES + ["duration_seconds", "congestion_ratio"])
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing columns in {data_path}: {missing}")

    df = df.dropna(subset=["duration_seconds", "congestion_ratio"]).copy()
    report_lines = [
        f"Source data: {data_path}",
        f"Rows used: {len(df)}",
        f"Training profile: {args.profile}",
        space_message,
        "",
    ]
    report_lines.extend(
        train_target(df, "congestion_ratio", "best_congestion_ratio_model.joblib", profile)
    )
    report_lines.extend(
        train_target(df, "duration_seconds", "best_duration_model.joblib", profile)
    )

    report_path = ARTIFACT_DIR / "traffic_model_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))


if __name__ == "__main__":
    main()
