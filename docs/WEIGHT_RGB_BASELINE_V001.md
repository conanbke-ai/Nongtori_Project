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

## Successor: RGB Multi-view V002

V001 aggregates all 22 view predictions with a simple arithmetic mean.

V002 keeps the same EfficientNet-B0 model family and tests only the fruit-level aggregation rule.

Fixed candidates:

```text
MEAN_22_VIEW
MEDIAN_22_VIEW
TRIMMED_MEAN_10PCT_EACH_TAIL
TRIMMED_MEAN_20PCT_EACH_TAIL
```

Development protocol:

```text
official train 367
→ FRUIT_ID 5-fold CV
→ per-fold checkpoint selected by predeclared MEAN_22_VIEW MAE
→ OOF view predictions
→ aggregation candidate selection from OOF fruit metrics
→ full official-train retrain at fixed epoch
→ official validation 79 confirmation
→ official test 78 remains locked
```

Selection priority:

1. grade error count
2. threshold crossing count
3. MAE
4. RMSE
5. least aggressive aggregation tie-break

Command:

```bash
python -m ml.weight_baseline.rgb_multiview_v002
```

This experiment is intentionally heavier than Geometry V2/V3 because it trains five fold models plus one final train-only model.

### Training terms: Fold / Epoch / Batch

RGB V002 uses three nested training units.

```text
5-fold cross-validation
└─ one Fold
   └─ multiple Epochs
      └─ multiple Batches
```

Definitions:

- **Fold**: one cross-validation round. The official train 367 FRUIT_ID are split into five groups. For a given fold, four groups are used for model fitting and the remaining group is a development holdout. Fold is not a batch.
- **Epoch**: one complete pass over every training view assigned to that fold. `EPOCH 01/15` means the model has completed the first full pass over that fold's training views, out of at most 15 passes.
- **Batch**: the small tensor group processed by the GPU in one optimizer step. V002 uses batch size 32.

Example for a 293-fruit fold:

```text
293 fruit × 22 views = 6,446 training views
6,446 / batch 32 ≈ 202 optimizer batches per epoch
```

So one fold can contain up to 15 epochs, and each epoch contains roughly 202 training batches. Early stopping may end the fold before epoch 15.

### DataLoader worker policy

Default: `workers=4`.

Workers are CPU-side DataLoader processes, not GPU workers. They prepare image batches by reading JPEG files, decoding images, resizing/cropping, applying augmentation, converting to tensors, and normalizing before the batch is transferred to the GPU.

Why 4 is the current default:

- each fold repeatedly loads thousands of JPEG views;
- EfficientNet-B0 batch size 32 benefits from overlapping CPU preprocessing with GPU computation;
- CUDA runs use `pin_memory=True` to improve host-to-device transfer;
- `persistent_workers=True` avoids respawning workers every epoch;
- on Windows, excessively high worker counts can increase process-spawn, RAM, context-switching, and storage-I/O overhead;
- therefore 4 is used as a conservative baseline that provides parallel preprocessing without aggressive multiprocessing.

`workers=4` is **not** claimed to be the hardware-optimal value.

Adjustment policy:

```text
default = 4
if GPU starvation / low throughput is observed:
    benchmark 2 / 4 / 6 / 8 workers
select using:
    epoch time + images/sec + GPU utilization + runtime stability
```

Do not change worker count solely because a higher number appears faster in theory.

### Runtime log / GPU policy

Because V002 performs five fold trainings plus one final fit, accidental CPU execution is blocked by default.

Startup logs must make the runtime environment visible:

- Python executable
- PyTorch version
- PyTorch CUDA build
- `torch.cuda.is_available()`
- selected GPU name
- fold/epoch progress and current metrics

If CUDA is unavailable, V002 exits with a diagnostic instead of silently starting CPU training.

Intentional CPU execution is possible only with:

```bash
python -m ml.weight_baseline.rgb_multiview_v002 --allow-cpu
```

## Next

After the real RGB-only result is recorded:

1. compare geometry-only vs RGB-only on the identical fruit test set;
2. inspect whether each model fails on the same fruit IDs;
3. only then evaluate a combined RGB + geometry model.
