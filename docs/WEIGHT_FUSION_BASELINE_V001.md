# WEIGHT Fusion Baseline V001

## Purpose

Evaluate whether Geometry V001 and RGB V001 provide useful complementary information without using the frozen test split for model selection.

The paired residual audit showed:

- RGB test MAE is lower than Geometry;
- Geometry test RMSE/R² and maximum-error tail are better;
- signed residual correlation is near zero;
- the diagnostic per-fruit oracle MAE is substantially below either individual baseline.

This justifies a controlled fusion experiment.

## Fixed fusion family

V001 uses a simple convex blend:

```text
fusion = alpha_rgb * RGB + (1 - alpha_rgb) * Geometry
```

Candidate `alpha_rgb` values are fixed before execution:

```text
0.0, 0.1, 0.2, ..., 1.0
```

No nonlinear stacker, tree model, neural fusion head, or test-driven search is allowed in V001.

## Selection split

`alpha_rgb` is selected on **validation only**.

The frozen test split does not participate in candidate ranking.

## Selection policy

Lexicographic validation ranking:

1. fewer weight-grade errors;
2. fewer total 12/16/22g threshold crossings;
3. lower MAE;
4. lower RMSE;
5. closer to equal blend (0.5) as a deterministic tie-break;
6. lower alpha as final deterministic tie-break.

This reflects Nongtori's operational priority: a small gram error can be more important when it crosses a grade boundary.

## Test policy

After validation selects one alpha, that alpha is frozen.

Train / validation / test metrics are then reported for the same selected fusion.

The test result is **report once / no test tuning**.

Changing test predictions must not change the selected alpha. This is covered by regression tests.

## Metrics

Each split reports:

- MAE
- RMSE
- R²
- bias
- max absolute error
- weight-grade accuracy
- grade error count
- severe grade error count
- total threshold crossings
- per-threshold 12 / 16 / 22 g crossing counts
- grade confusion

Geometry, RGB, and Fusion are reported side-by-side.

## Command

```bash
python -m ml.weight_baseline.fusion_v001 \
  --geometry artifacts/weight/geometry-v001/geometry_predictions.csv \
  --rgb artifacts/weight/rgb-v001/rgb_fruit_predictions.csv \
  --output-dir artifacts/weight/fusion-v001
```

Outputs:

- `fusion_baseline.json`
- `fusion_predictions.csv`

## Acceptance interpretation

V001 is not automatically accepted just because its validation score is best among candidate blends.

Interpret the final report against both individual baselines:

- Did fusion reduce validation grade errors?
- Did it reduce threshold crossings?
- Did it lower validation MAE without creating a worse outlier tail?
- On frozen test, does the already-selected fusion remain competitive without tuning?

If V001 does not provide a clear operational benefit, retain the simpler individual model or move to a later, separately specified fusion experiment.
