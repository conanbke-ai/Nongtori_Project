# EXP-RIP-005 — Label Smoothing

Status: **REJECTED / LOCAL GPU SCREENING / VALIDATION ONLY**

## Evidence

- Task: ripeness / maturity ordinal classification
- Change Category: `LOSS`
- Execution: local CUDA GPU
- GPU: NVIDIA GeForce RTX 4060 8GB
- PyTorch: `2.5.1+cu121`
- CUDA runtime: `12.1`
- Snapshot: `KGCV-RIPENESS-V001`
- Seed: `20260910`
- Test evaluated: **NO**
- Model: ImageNet-pretrained ResNet-18
- Fine tuning: full backbone from epoch 1
- Optimizer: AdamW
- LR: constant `5e-5`
- Weight decay: `1e-4`
- Batch size: 32
- Baseline loss: weighted CrossEntropy, `label_smoothing=0`
- Candidate loss: weighted CrossEntropy, `label_smoothing=0.05`
- Structured run id: `bc8ce459c1b6`
- Successful run duration: about `10:44`

## Observed Problem

After optimization experiments, the remaining known weakness was adjacent maturity-boundary confusion, historically concentrated around M0/M1.

## Hypothesis

Mild label smoothing could reduce over-confident boundary decisions and improve validation generalization without changing model architecture, data, split, augmentation, optimizer, learning rate, or checkpoint selection.

## Controlled Comparison

```text
Baseline
weighted CrossEntropy
label_smoothing = 0

Candidate
weighted CrossEntropy
label_smoothing = 0.05
```

All other relevant variables were fixed.

## Actual Result

| Metric | Baseline | Label smoothing 0.05 | Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9683** | 0.9631 | **-0.0052** |
| Accuracy | **0.9691** | 0.9650 | **-0.0041** |
| Ordinal MAE ↓ | **0.0432** | 0.0514 | **+0.0082** |
| Weighted Kappa | **0.9692** | 0.9663 | **-0.0029** |
| Best epoch | 2 | 6 | +4 |

The candidate changed the optimization trajectory and delayed the best checkpoint from epoch 2 to epoch 6, but the selected checkpoint was worse on every reported primary/ordinal metric.

The higher training and validation losses under label smoothing are expected because the loss target distribution itself changed, so raw loss magnitude is not compared directly across the two objectives. Model selection remains based on validation Macro F1 and supporting ordinal metrics.

## Interpretation

The hypothesis was not supported at `label_smoothing=0.05`.

The smoothing regularizer prevented the model from becoming as confident, but this did not improve the actual maturity decision boundary on the frozen validation split. The change therefore adds regularization without a compensating gain in classification or ordinal behavior.

Because the degradation is clear and all major metrics moved in the wrong direction, repeated micro-sweeps of neighboring smoothing values are not justified.

## Decision

`REJECT LABEL_SMOOTHING=0.05 FOR CURRENT RESNET-18 RECIPE`

Do not run `0.03`, `0.07`, `0.1`, etc. solely to chase a nearby optimum.

Keep the current confirmed recipe:

```text
ResNet-18
full fine-tuning from epoch 1
AdamW
constant LR = 5e-5
weighted CrossEntropy
label_smoothing = 0
selection = validation Macro F1
```

## Next Action

Move to a genuinely different loss mechanism that better matches the ordinal nature of maturity rather than continuing generic smoothing micro-tuning. Any next candidate must still be evaluated against Macro F1, per-class behavior, Ordinal MAE, Weighted Kappa, and confusion pattern.

## Reliability / Scope

- actual local GPU execution: YES
- frozen snapshot: YES
- controlled variable isolation: YES
- test tuning: NO
- screening evidence: YES
- multi-seed confirmation: NOT REQUIRED AFTER CLEAR REGRESSION
- field validation: NO
- production claim: NO

The shared immutable `KGCV-RIPENESS-V001` cache was materialized during this run. Future experiments using the same snapshot should reuse it instead of redownloading the 1,477 source images.
