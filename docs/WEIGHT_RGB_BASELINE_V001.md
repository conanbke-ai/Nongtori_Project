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

## Product role

RGB V001 is a **vision weight-estimation baseline**, not a claim that Nongtori should replace a physical scale.

The portfolio target harvesting hardware is not fixed, so this module proves that Nongtori can estimate weight without depending on a particular load-cell interface.

Future runtime priority:

```text
SENSOR_MEASURED
→ MANUAL_MEASURED
→ VISION_ESTIMATED
```

A trusted measured value should take precedence over the model estimate.

The RGB baseline remains useful for:

- pre-harvest weight/grade estimation;
- devices that do not expose weight measurement;
- sensor fallback;
- paired residual/fusion experiments with geometry.

See `WEIGHT_ESTIMATION_PRODUCT_ROLE_V1.md`.

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
- 12/16/22g weight-grade accuracy
- grade confusion
- 12g / 16g / 22g threshold crossing behavior
- error concentration by distance to the nearest grade boundary

A lower global MAE does not automatically imply a better operational model when boundary crossings increase.

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

## Recorded V001 result

Real run on `WEIGHT-DRYAD-V001`:

| Split | MAE | RMSE | R² | Grade accuracy |
|---|---:|---:|---:|---:|
| Train | 0.7315 g | 1.3387 g | 0.9607 | 89.37% |
| Validation | 1.5647 g | 2.3501 g | 0.8366 | 79.75% |
| Test | 1.2401 g | 2.3446 g | 0.8852 | 83.33% |

Additional test facts:

- bias: -0.4192 g
- max absolute error: 12.4082 g
- best epoch: 7
- early stop after epoch 11
- final recorded runtime device: CPU

Compared with Geometry V001 test, RGB lowers MAE and slightly improves weight-grade accuracy, but has worse RMSE/R² and a larger maximum error. The next step is therefore a paired residual audit, not an unconditional model replacement.

## Next

After the real RGB-only result is recorded:

1. compare geometry-only vs RGB-only on the identical fruit test set;
2. inspect whether each model fails on the same fruit IDs;
3. only then evaluate a combined RGB + geometry model.
