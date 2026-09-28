# WEIGHT Geometry Baseline V001

## Scope

This baseline is the first model stage after the immutable `WEIGHT-DRYAD-V001` snapshot.

It uses **fruit-level geometry only**:

- width
- height
- width × height

Target:

- `weight_with_calyx_g`

Atomic evaluation unit:

- `FRUIT_ID`

The 22 RGB views of one fruit are **not** treated as 22 independent geometry samples.

## Fixed models

The baseline reports three predeclared models:

1. `TRAIN_MEAN`
2. `LINEAR_WIDTH_HEIGHT`
3. `LINEAR_WIDTH_HEIGHT_AREA`

The primary model is fixed in advance as `LINEAR_WIDTH_HEIGHT_AREA`.
Validation performance is not used to select a winner in V001.

Linear models standardize geometry using train-split statistics only and solve a small ridge-stabilized normal equation. No external ML dependency is required.

## Metrics

Each train / validation / test split reports:

- MAE (g)
- RMSE (g)
- R²
- bias (g)
- max absolute error (g)
- weight-grade accuracy under the 12 / 16 / 22 g Nongtori thresholds
- grade confusion counts

## Test policy

The frozen test split is reported once for the fixed V001 baseline.

No test-set tuning, feature selection, hyperparameter search, or threshold optimization is permitted.

## Command

```bash
python -m ml.weight_baseline.geometry_v001 \
  --snapshot-dir data/snapshots/WEIGHT-DRYAD-V001 \
  --output-dir artifacts/weight/geometry-v001
```

Outputs:

- `geometry_baseline.json`
- `geometry_predictions.csv`

## Gate

Execution is blocked unless:

- `WEIGHT_SNAPSHOT.json` status is `WEIGHT_SNAPSHOT_FROZEN`
- split group is `FRUIT_ID`
- primary target is `weight_with_calyx_g`
- train / validation / test are all non-empty
- width and height are positive numeric values for every fruit

## Next stage

After the real geometry baseline result is frozen:

1. inspect residuals around 12 / 16 / 22 g boundaries;
2. run an RGB weight-regression baseline on the same immutable split;
3. compare geometry-only vs RGB-only;
4. test a combined RGB + geometry model only after both independent baselines are recorded.
