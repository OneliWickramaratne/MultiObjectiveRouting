# Testing Guide

## Start Backend

```powershell
cd C:\Users\antho\OneDrive\Documents\Hospital\backend
& C:\Users\antho\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Check Traffic Model Status

Use:

```text
GET /api/traffic/status
```

Expected without a Google key:

```json
{
  "google_api_enabled": false,
  "congestion_model_available": true,
  "duration_model_available": true,
  "feature_data_available": true
}
```

This means the system is using cached Google-shaped traffic data and trained models.

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

Look for:

```json
"Selected ml_traffic_risk_aware route by urgency-adjusted cost"
```

## Test Hospital Transfer and Automated Ambulance Dispatch

In the frontend:

1. Select `National Hospital Admin`.
2. Run a recommendation.
3. Click `Request` on a recommended hospital.
4. Select `Durdans Hospital Admin`.
5. Accept the pending transfer.
6. The system automatically assigns the best available ambulance.
7. Select `Ambulance Alpha 1 Crew`.
8. The assigned mission appears with pickup/dropoff controls.
9. Use `Start Pickup`, `Start Dropoff`, and `Complete`.

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

Without Google key, expected:

```json
"model_used": "trained_congestion_model",
"route_source": "cached_google_shaped_ml_features"
```

With Google key, expected if Google succeeds:

```json
"model_used": "live_google_routes_api",
"route_source": "live_google_routes_api"
```

## Collect Live Traffic Snapshot

Only works after setting:

```powershell
$env:GOOGLE_MAPS_API_KEY="your-key-here"
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

Run only when the drive has enough free space:

```powershell
cd C:\Users\antho\OneDrive\Documents\Hospital
& C:\Users\antho\AppData\Local\Programs\Python\Python313\python.exe ml\train_traffic_models.py --profile balanced
```

Available profiles:

```text
compact   smallest artifacts
balanced  recommended default
research  heavier final-experiment models
```

Outputs:

```text
ml/artifacts/best_congestion_ratio_model.joblib
ml/artifacts/best_duration_model.joblib
ml/artifacts/traffic_model_report.txt
```
