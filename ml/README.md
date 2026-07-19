# ML Module

This folder contains the urgency classification pipeline.

## Model Strategy

Start with three baselines:

1. Logistic Regression
2. Random Forest
3. Gradient Boosting

The recommended final model is the best-performing model on validation data, with a preference for Gradient Boosting if accuracy and explainability are both strong.

## Why This Fits the Project

The project data is tabular and partly synthetic. A deep neural network is not the best first choice because it needs more data, is harder to explain, and is less defensible for a research prototype with limited real clinical data.

## Commands

Generate synthetic data:

```powershell
python ml/generate_synthetic_transfer_data.py
```

Train and compare models:

```powershell
python ml/train_urgency_model.py
```

Train traffic/congestion models:

```powershell
python ml/train_traffic_models.py --profile balanced
```

Profiles:

- `compact`: fastest and smallest artifacts
- `balanced`: recommended default for strong models without huge files
- `research`: largest comparison models for final experiments, requires more disk/RAM

Outputs are written to `ml/artifacts/`.
