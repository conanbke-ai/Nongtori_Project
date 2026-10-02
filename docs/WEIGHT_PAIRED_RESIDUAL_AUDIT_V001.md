# WEIGHT Paired Residual Audit V001

## Purpose

Compare Geometry V001 and RGB V001 on the **same frozen WEIGHT-DRYAD-V001 fruit IDs**.

This stage answers a different question from ordinary model ranking:

> Do the two models fail on the same strawberries, and does RGB actually reduce operational grade-boundary errors?

The audit is analysis-only. It must not be used to tune test-set thresholds, fusion weights, or model-selection rules.

## Inputs

Geometry:

```text
artifacts/weight/geometry-v001/geometry_predictions.csv
```

Primary geometry prediction:

```text
linear_width_height_area_pred_g
```

RGB:

```text
artifacts/weight/rgb-v001/rgb_fruit_predictions.csv
```

Primary RGB prediction:

```text
predicted_weight_g
```

The audit requires exact agreement on:

- `fruit_id` set
- split assignment
- `actual_weight_g`

## Metrics

For each train / validation / test split:

### Independent model metrics

- MAE
- RMSE
- R²
- bias
- max absolute error
- weight-grade accuracy
- severe grade errors
- 12 / 16 / 22 g threshold crossing counts

### Paired diagnostics

- RGB lower absolute error count
- Geometry lower absolute error count
- exact ties
- both-grade-correct / geometry-only-correct / RGB-only-correct / both-wrong
- geometry threshold crossings resolved by RGB
- threshold crossings introduced by RGB
- shared threshold crossings
- signed residual Pearson correlation
- absolute residual Pearson correlation
- diagnostic oracle lower-bound MAE

The oracle metric uses `min(|geometry_error|, |rgb_error|)` per fruit and is **diagnostic only**. It is not a deployable model.

## Boundary analysis

Results are grouped by distance from the nearest fixed Nongtori weight threshold:

- <=0.5 g
- <=1.0 g
- <=2.0 g
- <=3.0 g
- >3.0 g

This is important because a small numerical error can create a larger operational error if it crosses 12 / 16 / 22 g.

## Command

```bash
python -m ml.weight_baseline.compare_v001 \
  --geometry artifacts/weight/geometry-v001/geometry_predictions.csv \
  --rgb artifacts/weight/rgb-v001/rgb_fruit_predictions.csv \
  --output-json artifacts/weight/paired-v001/paired_residual_audit.json \
  --output-csv artifacts/weight/paired-v001/paired_residuals.csv
```

## Decision rule

Do **not** declare RGB or Geometry the final winner from global MAE alone.

Interpretation should consider:

1. test MAE / RMSE / R²;
2. grade accuracy;
3. threshold crossings;
4. large-outlier regressions;
5. residual correlation / complementarity.

A future RGB + Geometry fusion experiment is justified only if paired residuals show useful complementarity. Fusion hyperparameters must be selected on development data only; the frozen test split is report-only.
