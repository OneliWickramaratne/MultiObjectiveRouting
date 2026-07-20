# Evaluation Results

Two experiments were run against the actual project code (not simulated) to
turn design claims into measured findings.

## 1. Urgency Classification Model Comparison

Trained on `ml/artifacts/synthetic_transfer_data.csv` (1,000 synthetic
transfer scenarios), 80/20 stratified train/test split, evaluated on a
200-sample held-out test set.

| Model | Accuracy | Macro F1 | Critical-class F1 | Critical-class Recall |
|---|---|---|---|---|
| Logistic Regression | 84.5% | 0.84 | 0.77 | 0.74 |
| Random Forest | 84.0% | 0.83 | 0.78 | 0.74 |
| **Gradient Boosting** | **85.0%** | **0.85** | **0.80** | **0.79** |

**Finding:** Gradient Boosting achieved the highest overall accuracy and,
more importantly for a triage context, the best recall on the "critical"
class (0.79 vs. 0.74 for the other two models). Since a missed critical
case (false negative) is clinically more costly than an over-triaged
moderate case, recall on the critical class is a more meaningful
comparison metric than raw accuracy alone. This is the model selected and
saved as the production urgency-prediction artifact.

Full classification reports for all three models are in
`ml/artifacts/model_report.txt`.

## 2. Routing Strategy Evaluation: Shortest-Time vs. Urgency-Aware Risk Routing

24 route comparisons were run directly against `RoutingService.compare_routes`
across 8 real origin-destination hospital pairs, each evaluated at all three
urgency levels (critical / high / moderate).

| Urgency | Avg. extra travel time vs. shortest-time route | Avg. road-risk reduction | % risk reduction |
|---|---|---|---|
| Critical | +0.01 min | −0.090 | 14.5% |
| High | +0.05 min | −0.098 | 15.7% |
| Moderate | +0.13 min | −0.110 | 17.7% |

**Finding:** The urgency-aware routing strategy consistently reduces road
risk exposure relative to the shortest-time baseline across every urgency
level, while the time cost of doing so scales exactly as intended by the
routing weight design (critical: time 0.75 / risk 0.20 / distance 0.05;
moderate: time 0.45 / risk 0.40 / distance 0.15 — see Chapter 7). For
critical transfers, the system finds a lower-risk route at effectively no
time penalty (+0.01 min average); for moderate transfers, it accepts
roughly 10x more time cost (+0.13 min average) in exchange for a larger
risk reduction (17.7% vs. 14.5%). This confirms that the urgency-sensitive
weighting scheme produces its intended behavior in practice, not just in
design.

Raw per-pair results are available in `routing_eval_results.csv`.
