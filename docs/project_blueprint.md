# Project Blueprint

## Project Goal

Build an ICU capacity-aware decision-support system for emergency inter-hospital transfers in Colombo. The system should recommend a suitable receiving hospital and route by combining ICU availability, hospital capability, patient urgency, travel time, and route safety.

## Core Modules

### 1. Hospital Capacity Module

Stores selected Colombo hospitals, ICU capabilities, total ICU beds, occupied ICU beds, and supported emergency categories.

MVP behavior:

- Filter hospitals by required ICU type.
- Exclude hospitals with no available ICU beds.
- Rank hospitals using capability match, availability, distance, travel time, and route risk.

Future behavior:

- Hospital staff update bed status in near real time.
- Audit trail for bed updates.
- Role-based access for hospital admins.

### 2. Patient Condition Module

Converts patient condition inputs into an urgency score.

Recommended model strategy:

- MVP: rule-based triage score so the system is explainable and works before real data is available.
- Academic ML baseline: Logistic Regression, Random Forest, and Gradient Boosting on synthetic patient transfer scenarios.
- Best practical model after evaluation: Gradient Boosted Trees, such as XGBoost or LightGBM, because tabular clinical scenario data is usually small-to-medium sized and structured.

Why not deep learning first:

- The proposal relies on synthetic and limited real data.
- Deep learning needs more data and is harder to justify.
- Gradient boosted trees are stronger for tabular datasets, easier to evaluate, and more explainable with feature importance / SHAP.

Input features:

- Condition type: trauma, cardiac, respiratory, surgical, neuro, sepsis
- Vital severity: oxygen saturation band, blood pressure band, consciousness level
- Required ICU type
- Transfer priority: critical, high, moderate
- Age band, optional
- Ventilator required, yes/no

Output:

- Urgency class: critical, high, moderate
- Numeric urgency score from 0 to 1

### 3. Road Network Module

Uses OpenStreetMap data to represent Colombo roads as a weighted graph.

Graph attributes:

- Road segment length
- Estimated travel time
- Road class
- Junction complexity
- Railway crossing proximity
- Hospital access proximity

MVP options:

- Use OSMnx to download and build a local road graph.
- Use NetworkX for routing experiments.
- Store final graph or route metadata in PostGIS.

Production-style options:

- Use OSRM, GraphHopper, Valhalla, or pgRouting for faster routing.
- Add a traffic provider only if allowed by budget and API terms.

### 4. Multi-Objective Routing Engine

The routing engine should not simply choose shortest distance. It should calculate a weighted route cost:

```text
route_cost =
  time_weight * normalized_travel_time +
  risk_weight * normalized_route_risk +
  distance_weight * normalized_distance
```

Weights adapt by urgency:

| Urgency | Time Weight | Risk Weight | Distance Weight |
| --- | ---: | ---: | ---: |
| Critical | 0.75 | 0.20 | 0.05 |
| High | 0.60 | 0.30 | 0.10 |
| Moderate | 0.45 | 0.40 | 0.15 |

This gives the research a clear comparison:

- Baseline: shortest-time route
- Proposed: urgency-aware multi-objective route

### 5. Decision-Support Interface

Primary screens:

- Transfer planner
- Hospital availability map
- Route comparison view
- ICU capacity admin panel
- Scenario simulation dashboard

Transfer planner flow:

1. Select origin hospital.
2. Enter patient condition.
3. Choose required ICU type.
4. System ranks receiving hospitals.
5. User selects a recommendation.
6. System displays route, travel time, risk score, and reason for recommendation.

## Database

Use PostgreSQL plus PostGIS.

Main entities:

- hospitals
- icu_units
- icu_bed_status
- patients_or_scenarios
- transfer_requests
- route_options
- route_risk_features
- users
- audit_logs

See `docs/database_schema.md`.

## API Design

Core API groups:

- `/api/hospitals`
- `/api/icu-status`
- `/api/transfers`
- `/api/routes`
- `/api/predictions`
- `/api/simulations`

See `docs/api_contract.md`.

## Evaluation Plan

Compare the proposed DSS against shortest-time routing.

Metrics:

- Recommended destination has matching ICU capability
- Recommended destination has available ICU bed
- Estimated transfer time
- Route safety score
- System response time
- Recommendation explanation quality

Experiments:

- Different urgency levels
- Different ICU occupancy levels
- Different origin hospitals
- Infrastructure risk enabled vs disabled
- Shortest-time route vs proposed multi-objective route

## Build Phases

### Phase 1: Research MVP

- Seed Colombo hospital dataset
- Synthetic ICU occupancy generator
- Rule-based urgency scoring
- Basic route ranking
- FastAPI backend
- React map UI

### Phase 2: ML and Optimization

- Generate synthetic patient transfer dataset
- Train urgency classification models
- Evaluate Logistic Regression, Random Forest, Gradient Boosting
- Add route risk scoring
- Compare route algorithms

### Phase 3: Full Prototype

- Admin panel for ICU status updates
- Scenario simulation module
- Route comparison visualization
- Exportable evaluation results

### Phase 4: Research Report Evidence

- Run simulation experiments
- Generate charts and tables
- Document limitations
- Prepare demonstration script
