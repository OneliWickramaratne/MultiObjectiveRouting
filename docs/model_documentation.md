# Model Documentation

Last reviewed: 2026-07-13

## Decision-Support Position

Models in this project support human decisions. They must not independently make final medical or operational decisions. Mandatory clinical eligibility rules must remain separate from ranking scores.

## Urgency Scoring

- Service: `backend/app/services/urgency_service.py`
- Type: deterministic rules
- Inputs: condition type, oxygen band, blood pressure band, consciousness, ventilator requirement, required ICU type.
- Outputs: urgency class, urgency score, explanation.
- Limitations: not clinically validated; should be reviewed by clinicians before real use.
- Baseline: this rule set is the baseline.

## Traffic and Travel-Time Prediction

- Service: `backend/app/services/traffic_model_service.py`
- Type: joblib-loaded scikit-learn models when present; deterministic fallback otherwise.
- Inputs: hospital pair, time features, distance, static route duration, OSM intersections/signals/risk, road mix, historical traffic interval features.
- Outputs: predicted duration seconds, congestion ratio, route risk score, model source.
- Artifacts searched:
  - `ml/artifacts/best_congestion_ratio_model.joblib`
  - `_incoming_hos_zip/HOS/best_congestion_ratio_model.joblib`
  - `_incoming_hos_zip/HOS/best_duration_model.joblib`
  - `data/traffic_model_ready.csv`
- Limitations:
  - Training provenance and validation metrics are not yet documented in a model card.
  - Missing/failed model load silently uses deterministic fallback.
  - No drift monitoring.
  - No model version included in API response yet.

## OSM Routing and Risk

- Service: `backend/app/services/osm_graph_routing_service.py`
- Type: deterministic graph routing using NetworkX A*.
- Inputs: origin/destination coordinates, strategy, urgency class, congestion ratio.
- Outputs: node IDs, polyline, route steps, risk features, risk factors, explanation.
- Strategies:
  - `shortest_time`
  - `ml_traffic_risk_aware`
- Limitations:
  - No live road closure feed.
  - No bounded timeout/circuit breaker yet.
  - Nearest-node lookup is vectorized but not spatial-indexed.

## Ambulance Dispatch Scoring

- Service: `backend/app/services/dispatch_service.py`
- Type: deterministic weighted scoring.
- Inputs: ambulance location/status/base, origin hospital, urgency, OSM pickup route, traffic congestion, base coverage.
- Outputs: selected ambulance, score, pickup ETA, risk, coverage penalty, explanation, candidate rankings.
- Limitations:
  - No vehicle capability/equipment model yet.
  - No driver shift/fatigue status.
  - No atomic assignment lock yet.

## Capacity Forecasting

- Service: `backend/app/services/capacity_forecast_service.py`
- Type: deterministic forecast from current beds, inbound transfers, recent release rate, cleaning recovery.
- Outputs: predicted available/occupied beds by horizon and pressure level.
- Limitations:
  - Forecast is not a confirmed bed count.
  - No confidence interval yet.
  - No validation against historical outcomes yet.

## Simulation Analytics

- Service: `backend/app/services/simulation_analytics_service.py`
- Type: read-only scenario calculation.
- Scenarios: baseline, evening surge, mass casualty, respiratory wave.
- Outputs: simulated transfer load, critical cases, ambulance gap, bed shortage, hospital impacts.
- Safety: does not mutate live transfer, patient, ambulance, or bed records.

## Required Model Registry Fields

Before production, each model artifact must include:

- model id
- model version
- training date
- training data source
- feature list
- preprocessing version
- validation method
- metrics
- calibration result
- limitations
- fallback behavior
- owner
- rollback artifact
