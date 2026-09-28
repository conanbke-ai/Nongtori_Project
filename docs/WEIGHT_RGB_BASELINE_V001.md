# WEIGHT RGB Baseline V001

## Scope

This baseline is the RGB-only comparison stage for the frozen `WEIGHT-DRYAD-V001` snapshot.

- training unit: one RGB view
- evaluation unit: one `FRUIT_ID`
- each fruit has exactly 22 views
- fruit prediction = mean of the 22 view-level predictions
- primary target: `weight_with_calyx_g`
- split boundary remains `FRUIT_ID`

This prevents 22 views of one physical strawberry from being counted as 22 independent evaluation samples.

## Fixed V001 model

- EfficientNet-B0
- ImageNet-1K pretrained weights
- 224x224 input after resize/center crop
- SmoothL1 loss, beta=1.0
- AdamW
- learning rate: 1e-4
- weight decay: 1e-4
- batch size: 32
- max epochs: 15
- patience: 4
- gradient clipping: 5.0
- train augmentation: horizontal flip only
- seed: 20260928

The baseline is intentionally narrow. V001 does not perform architecture search, learning-rate search, augmentation search, or test-set tuning.

## Checkpoint policy

Checkpoint selection uses validation **fruit-level MAE**, not per-view loss.

The frozen test split is evaluated only after the best validation checkpoint is loaded.

## Metrics

At fruit level:

- MAE
- RMSE
- R²
- bias
- max absolute error
- 12/16/22g grade accuracy
- grade confusion

View-level SmoothL1 loss is retained as a training diagnostic only.

## Command

```bash
python -m ml.weight_baseline.rgb_v001 \
  --snapshot-dir data/snapshots/WEIGHT-DRYAD-V001 \
  --output-dir artifacts/weight/rgb-v001 \
  --workers 4
```

RTX/CUDA is selected automatically when available.

## Outputs

- `best.pt`
- `training_history.json`
- `rgb_fruit_predictions.csv`
- `rgb_baseline.json`

## Next

After the real RGB-only result is recorded:

1. compare geometry-only vs RGB-only on the identical fruit test set;
2. inspect whether each model fails on the same fruit IDs;
3. only then evaluate a combined RGB + geometry model.
