# API Contract

Base path: `/api`

This documents the actual implemented endpoints, verified directly
against the route handlers in `backend/app/api/routes/`. This replaces
an earlier draft that described a different, simplified API shape (a
separate `/icu-status` and `/simulations` group) written during initial
planning — those were consolidated into the richer admin/ambulance
endpoint groups documented in `docs/current_system_architecture.md`
during implementation. This document covers the public/core endpoints;
see that document for the full authenticated admin and ambulance crew
endpoint list.

## Hospitals

### `GET /hospitals`

Returns all hospitals with location, real per-ward ICU capability
(derived from bed records, not a single label — a hospital can run more
than one ICU specialty), and current capacity.

Query parameters:

- `icu_type` (optional) — filter to hospitals supporting this ICU type
- `has_available_bed` (optional, boolean, default `false`) — filter to
  hospitals with at least one available bed

Response (one item per hospital):

```json
{
  "id": "1",
  "name": "National Hospital Sri Lanka",
  "latitude": 6.918611,
  "longitude": 79.868889,
  "icu_types": ["Trauma ICU", "General ICU", "Cardiac ICU"],
  "total_beds": 20,
  "occupied_beds": 18,
  "available_beds": 2,
  "supports_trauma": true,
  "supports_cardiac": true,
  "supports_neuro": true,
  "supports_pediatric": false,
  "supports_maternity": false,
  "has_ventilator_support": true
}
```

### `GET /hospitals/{hospital_id}`

Returns the same shape as above for a single hospital. `hospital_id`
accepts either the numeric id (e.g. `"1"`) or a known alias (e.g.
`"nhsl"`) — aliases are resolved server-side.

## Predictions

### `POST /predictions/urgency`

Predicts patient urgency from the deterministic rule-based scoring
service (see `docs/model_documentation.md`).

Request:

```json
{
  "condition_type": "respiratory",
  "oxygen_saturation_band": "low",
  "blood_pressure_band": "unstable",
  "consciousness_level": "reduced",
  "ventilator_required": true,
  "required_icu_type": "General ICU"
}
```

Response:

```json
{
  "urgency_class": "critical",
  "urgency_score": 0.91,
  "explanation": [
    "Low oxygen saturation",
    "Ventilator required",
    "Reduced consciousness"
  ]
}
```

## Transfers

### `POST /transfers/recommend`

Recommends destination hospitals ranked by urgency-adjusted route cost,
filtered by real per-ward ICU bed availability (not a hospital-wide
aggregate).

Request:

```json
{
  "origin_hospital_id": "nhsl",
  "required_icu_type": "General ICU",
  "patient_condition": {
    "condition_type": "respiratory",
    "oxygen_saturation_band": "low",
    "blood_pressure_band": "unstable",
    "consciousness_level": "reduced",
    "ventilator_required": true
  }
}
```

Response:

```json
{
  "urgency_class": "critical",
  "urgency_score": 0.91,
  "recommendations": [
    {
      "destination_hospital_id": "9",
      "destination_name": "Durdans Hospital",
      "rank": 1,
      "score": 0.87,
      "available_beds": 3,
      "estimated_minutes": 7.6,
      "route_risk_score": 0.56,
      "reasons": [
        "Matching ICU capability",
        "3 General ICU bed(s) available",
        "Selected ml_traffic_risk_aware route by urgency-adjusted cost"
      ]
    }
  ]
}
```

`available_beds` and the "bed(s) available" reason reflect availability
of the **specific requested ICU type**, not the hospital's total bed
count.

For creating an actual transfer request from a recommendation, accepting
it, and the full operational lifecycle (bed reservation, automated
ambulance dispatch, mission tracking), see the authenticated
`/api/admin/transfers` and `/api/ambulance/mission` endpoint groups in
`docs/current_system_architecture.md`.

## Routes

### `POST /routes/optimize`

Returns both route strategies (shortest-time and urgency-aware
risk-routing) between two hospitals, computed over the real Colombo OSM
road graph.

Request:

```json
{
  "origin_hospital_id": "nhsl",
  "destination_hospital_id": "2",
  "urgency_class": "critical"
}
```

Response (abbreviated — `route_nodes`, `route_steps`, `polyline`, and
`risk_features` omitted for brevity):

```json
{
  "routes": [
    {
      "strategy": "shortest_time",
      "estimated_minutes": 13.9,
      "distance_km": 6.1,
      "risk_score": 0.62,
      "total_cost": 0.41,
      "congestion_ratio": 1.24,
      "model_used": "trained_congestion_model",
      "route_source": "cached_google_shaped_ml_features",
      "explanation": ["Weighted shortest-time path"]
    },
    {
      "strategy": "ml_traffic_risk_aware",
      "estimated_minutes": 13.9,
      "distance_km": 6.3,
      "risk_score": 0.54,
      "total_cost": 0.35,
      "congestion_ratio": 1.24,
      "model_used": "trained_congestion_model",
      "route_source": "cached_google_shaped_ml_features",
      "explanation": ["Selected ml_traffic_risk_aware route by urgency-adjusted cost"]
    }
  ]
}
```

`model_used` and `route_source` report `"live_google_routes_api"` when a
`GOOGLE_MAPS_API_KEY` is configured and the live call succeeds, falling
back to `"trained_congestion_model"` / `"cached_google_shaped_ml_features"`
otherwise — see the routing fallback chain in
`docs/current_system_architecture.md`.

## Traffic

### `GET /traffic/status`

Reports whether trained traffic models and cached feature data are
loaded.

```json
{
  "google_api_enabled": false,
  "congestion_model_available": true,
  "duration_model_available": true,
  "feature_data_available": true,
  "feature_data_rows": 21504,
  "congestion_model_path": "ml/artifacts/best_congestion_ratio_model.joblib",
  "duration_model_path": "ml/artifacts/best_duration_model.joblib",
  "feature_data_path": "data/traffic_model_ready.csv"
}
```

### `POST /traffic/collect-snapshot`

Collects a live traffic snapshot via the Google Routes API. Only
functional when `GOOGLE_MAPS_API_KEY` is set.

```json
{
  "origin_hospital_ids": ["1"],
  "destination_hospital_ids": ["2"],
  "departure_time_iso": null
}
```

Appends rows to `data/traffic_observations_live.csv`.

## Authenticated Admin and Ambulance Endpoints

Dashboard, capacity forecasting, simulation, ICU bed management, transfer
creation/accept/reject, and ambulance mission endpoints all require a
bearer access token and are documented in full in
`docs/current_system_architecture.md` under "API Endpoints".
