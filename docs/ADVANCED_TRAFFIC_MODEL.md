# Advanced Traffic and Route-Risk Model

## Verdict

Using real traffic data from Google Routes API plus structural road-risk features from OpenStreetMap is a strong idea for this project.

The best design is not one huge model that decides everything. The strongest architecture is a hybrid decision system:

- Deterministic filtering for hospital suitability and ICU availability
- ML regression for traffic-adjusted ETA / congestion
- OSM feature engineering for structural route risk
- Multi-objective optimization for final hospital and route ranking

This is more defensible than using machine learning everywhere blindly.

## Data Sources

### Google Routes API

Use for time-sensitive traffic labels:

- distance meters
- static duration
- traffic-aware duration
- congestion ratio
- route polyline if collected

The current imported dataset already follows this shape:

- `traffic_observations.csv`
- `traffic_model_ready.csv`
- `hospital_pairs.csv`
- `best_congestion_ratio_model.joblib`
- `best_duration_model.joblib`

### OpenStreetMap

Use for risk and route structure:

- intersections
- traffic signals
- road class mix
- railway crossings
- complex junctions
- one-way / narrow roads where available

## Recommended Model Design

### Model 1: Congestion Ratio Regressor

Target:

```text
congestion_ratio = traffic_duration_seconds / static_duration_seconds
```

Recommended algorithms:

- LightGBM / XGBoost if available
- Random Forest as strong baseline
- Gradient Boosting as interpretable baseline

Why:

- The data is tabular
- Features include time, route, traffic, road mix, and hospital pair
- Tree-based models handle nonlinear effects well

### Model 2: Duration Regressor

Target:

```text
duration_seconds
```

This can be used as a second model or fallback check against:

```text
static_duration_seconds * predicted_congestion_ratio
```

### Model 3: Route Risk Model

For the first research prototype, risk can be a transparent weighted score:

```text
risk =
  intersection_weight * intersections_per_km +
  signal_weight * signals_per_km +
  railway_weight * railway_crossings +
  junction_weight * complex_junctions +
  local_road_weight * local_road_ratio
```

Only train a route-risk ML model if you can collect labels such as historical ambulance delay, incident frequency, or expert-rated risk. Without labels, a transparent engineered score is academically stronger.

## Final Ranking

Rank candidate hospitals after filtering by ICU capability and availability.

Recommended score:

```text
final_score =
  eta_weight * eta_score +
  risk_weight * risk_score +
  bed_weight * bed_availability_score +
  capability_weight * capability_match_score
```

Urgency-specific weights:

| Urgency | ETA | Risk | Beds | Capability |
| --- | ---: | ---: | ---: | ---: |
| Critical | 0.55 | 0.25 | 0.10 | 0.10 |
| High | 0.45 | 0.30 | 0.15 | 0.10 |
| Moderate | 0.35 | 0.35 | 0.20 | 0.10 |

## Current Backend Integration

The backend now supports:

- 9-hospital dataset from the previous notebook
- ICU type normalization
- condition capability filtering
- ventilator filtering
- trained traffic model loading when model files exist
- fallback ETA/risk calculation when model files are unavailable

The traffic model service looks for files in:

```text
ml/artifacts/best_congestion_ratio_model.joblib
ml/artifacts/best_duration_model.joblib
data/traffic_model_ready.csv
```

It also falls back to the imported local zip extraction path:

```text
_incoming_hos_zip/HOS/
```

## When the Google API Key Is Needed

The backend does not need a Google API key for:

- testing `/api/hospitals`
- testing `/api/predictions/urgency`
- using cached `traffic_model_ready.csv`
- using the trained congestion model already imported from the previous project
- fallback OSM-style ETA/risk estimates

The key is needed only when you want live Google Routes API behavior:

- live traffic-aware duration
- live static duration
- live distance
- real route polyline geometry for the frontend map
- collecting new traffic observations for retraining

Set it as:

```powershell
$env:GOOGLE_MAPS_API_KEY="your-key-here"
```

Then restart the backend.

When the key is present, `/api/routes/optimize` will try live Google Routes API first. If Google fails or the key is missing, it falls back to the trained model and cached route features.

## Next Improvements

1. Add a live Google Routes collection endpoint or scheduled collector.
2. Decode and store Google route polylines.
3. Download Colombo OSM using OSMnx and extract traffic lights / junction risk.
4. Generate several candidate routes, not only one shortest route.
5. Predict ETA and risk for each route candidate.
6. Return the Pareto-front route choices: fastest, safest, and balanced.
7. Log all recommendations for evaluation.
