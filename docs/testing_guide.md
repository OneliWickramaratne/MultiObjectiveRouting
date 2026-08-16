# Testing Guide

This guide assumes the virtual environment and `.env` already exist. On a
fresh clone, follow "First-time setup" in the root `README.md` first.

## Run the Unit Tests

From `backend/`. The suite is plain `unittest` and needs nothing beyond
`requirements.txt`:

```bash
python -m unittest discover -s tests -t .
```

## Start Backend

```bash
cd backend
source .venv/bin/activate
export DEV_SEED_PASSWORD="your-local-dev-password"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open:

```text
http://127.0.0.1:8001/docs
```

## Check Traffic Model Status

Use:

```text
GET /api/traffic/status
```

The `.joblib` artifacts are gitignored, so a fresh clone reports `false` for
both models until they are regenerated (see "Train Traffic Models" below).
The backend also logs a warning at startup when they are missing.

Expected without a Google key, once the models have been trained:

```json
{
  "google_api_enabled": false,
  "congestion_model_available": true,
  "duration_model_available": true,
  "feature_data_available": true
}
```

This means the system is using cached Google-shaped traffic data and
trained models rather than the time-of-day fallback formula.

## Test Recommendation

Use:

```text
POST /api/transfers/recommend
```

Body:

```json
{
  "origin_hospital_id": "nhsl",
  "required_icu_type": "General ICU",
  "patient_condition": {
    "condition_type": "trauma",
    "oxygen_saturation_band": "low",
    "blood_pressure_band": "unstable",
    "consciousness_level": "reduced",
    "ventilator_required": true
  }
}
```

`origin_hospital_id` accepts either the numeric hospital id (`"1"`) or a
known alias (`"nhsl"`) — aliases are resolved server-side against the
live database.

Look for:

```json
"Selected ml_traffic_risk_aware route by urgency-adjusted cost"
```

## Test Hospital Transfer and Automated Ambulance Dispatch

In the frontend (`http://localhost:5173`):

1. Log in as a hospital admin (e.g. username matching a hospital's
   admin account — see `backend/scripts/set_user_password.py` or query
   the `users` table for exact usernames).
2. Go to **Transfer planner**, fill in the patient/condition fields, and
   run a recommendation.
3. Click **Request transfer** on a recommended hospital.
4. Log out, log in as the **destination** hospital's admin.
5. Go to **Requests**, accept the pending transfer.
6. The system automatically assigns the best available ambulance.
7. Log out, log in as the assigned ambulance's crew account.
8. The **Active mission** page shows pickup/dropoff controls.
9. Use **Start pickup**, **Patient onboard**, and **Complete transfer**.

Backend endpoints:

```text
POST /api/admin/transfers
POST /api/admin/transfers/{transfer_id}/accept
GET /api/ambulance/mission
POST /api/ambulance/mission/{transfer_id}/start-pickup
POST /api/ambulance/mission/{transfer_id}/arrive-pickup
POST /api/ambulance/mission/{transfer_id}/complete
```

## Test Route Optimization

Use:

```text
POST /api/routes/optimize
```

Body:

```json
{
  "origin_hospital_id": "nhsl",
  "destination_hospital_id": "2",
  "urgency_class": "critical"
}
```

Without a Google key, expected:

```json
"model_used": "trained_congestion_model",
"route_source": "cached_google_shaped_ml_features"
```

With a Google key configured, expected if the live call succeeds:

```json
"model_used": "live_google_routes_api",
"route_source": "live_google_routes_api"
```

## Collect Live Traffic Snapshot

Only works after setting:

```bash
export GOOGLE_MAPS_API_KEY="your-key-here"
```

Use:

```text
POST /api/traffic/collect-snapshot
```

Body:

```json
{
  "origin_hospital_ids": ["1"],
  "destination_hospital_ids": ["2"],
  "departure_time_iso": null
}
```

Rows are appended to:

```text
data/traffic_observations_live.csv
```

## Train Traffic Models

Required on a fresh clone: the artifacts are gitignored, and without them
travel times fall back to the deterministic formula.

```bash
python ml/train_traffic_models.py
```

Available profiles, via `--profile`:

```text
compact   smallest artifacts
balanced  recommended default, used when --profile is omitted
research  heavier final-experiment models
```

The script refuses to start if it detects less free disk space than the
chosen profile needs. Override that check with `--skip-space-check`.

Outputs:

```text
ml/artifacts/best_congestion_ratio_model.joblib
ml/artifacts/best_duration_model.joblib
ml/artifacts/traffic_model_report.txt
```

## Reproduce the Quantitative Evaluation Results

Five findings in `docs/evaluation_results.md` are each backed by a real,
runnable script — none of the numbers or charts were hand-drawn:

```bash
cd ml
python generate_urgency_chart.py
```

```bash
cd backend
python scripts/eval_routing.py
python scripts/generate_routing_chart.py
python scripts/eval_dispatch.py
python scripts/generate_dispatch_chart.py
python scripts/eval_simulation.py
python scripts/generate_capacity_chart.py
```

The traffic model comparison is trained by the same script used to produce
the artifacts:

```bash
python ml/train_traffic_models.py
```

It reports MAE, RMSE and R² for random forest, extra trees and gradient
boosting on both targets, and writes the full comparison to
`ml/artifacts/traffic_model_report.txt`.

The urgency comparison in section 1 is reproduced by:

```bash
python ml/train_urgency_model.py
```

which writes `ml/artifacts/model_report.txt` with the per-model
classification reports.
