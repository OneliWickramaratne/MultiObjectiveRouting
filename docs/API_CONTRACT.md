# API Contract

Base path: `/api`

## Hospitals

### `GET /hospitals`

Returns hospitals with location, ICU capabilities, and current capacity summary.

Query parameters:

- `icu_type`
- `has_available_bed`
- `condition_type`

### `GET /hospitals/{hospital_id}`

Returns detailed hospital profile.

## ICU Status

### `PATCH /icu-status/{icu_unit_id}`

Updates occupied beds for an ICU unit.

Request:

```json
{
  "occupied_beds": 8,
  "updated_by": "hospital-admin"
}
```

## Predictions

### `POST /predictions/urgency`

Predicts patient urgency.

Request:

```json
{
  "condition_type": "respiratory",
  "oxygen_saturation_band": "low",
  "blood_pressure_band": "unstable",
  "consciousness_level": "reduced",
  "ventilator_required": true,
  "required_icu_type": "medical"
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

Recommends destination hospitals and route options.

Request:

```json
{
  "origin_hospital_id": "nhsl",
  "required_icu_type": "medical",
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
  "recommendations": [
    {
      "destination_hospital_id": "lrh",
      "rank": 1,
      "score": 0.87,
      "available_beds": 2,
      "estimated_minutes": 14,
      "route_risk_score": 0.22,
      "reasons": [
        "Matching ICU capability",
        "Available ICU beds",
        "Lowest urgency-adjusted route cost"
      ]
    }
  ]
}
```

## Routes

### `POST /routes/optimize`

Returns route options between two hospitals.

Request:

```json
{
  "origin_hospital_id": "nhsl",
  "destination_hospital_id": "lrh",
  "urgency_class": "critical"
}
```

Response:

```json
{
  "routes": [
    {
      "strategy": "multi_objective",
      "estimated_minutes": 14,
      "distance_km": 5.2,
      "risk_score": 0.22,
      "polyline": []
    },
    {
      "strategy": "shortest_time",
      "estimated_minutes": 12,
      "distance_km": 4.8,
      "risk_score": 0.44,
      "polyline": []
    }
  ]
}
```
