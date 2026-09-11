# RIPENESS-BASELINE-V001 Result

Status: **REPRODUCED / EXTERNAL-DOMAIN BASELINE**

## 1. Run identity

- Experiment: `RIPENESS-BASELINE-V001`
- Snapshot: `KGCV-RIPENESS-V001`
- Snapshot assignment SHA-256: `5e2424f7c26d84e4f8d43ca90ba60b46806eb9d7bb361669c8b42ad27f2040ea`
- Model: ImageNet-pretrained ResNet-18
- Seed: `20260910`
- Physical source images: 1,477
- Eligible object crops: 3,162
- Split: train 2,243 / valid 486 / test 433
- Run duration: 1,344.188 s (22m 24s)
- Errors: 0
- Warnings: 5 (validation non-improvement / early-stopping counter)

## 2. Best validation checkpoint

- Best epoch: **1**
- Best validation Macro F1: **0.9536944102**
- Checkpoint SHA-256: `e9a746113d6d28edb481665ae23b59d9bf542dc9f9da3fb7465488cb2aea8a17`
- Early stopping triggered at epoch 6 after five consecutive non-improving epochs.

The fact that epoch 1 remained the best checkpoint while train loss continued to fall is treated as a strong sign that the initial full fine-tuning schedule is overfitting quickly. This is a baseline diagnostic, not a final training recipe.

## 3. Frozen test result

| Metric | Result |
|---|---:|
| Accuracy | 0.9422632794 |
| Macro F1 | 0.9402391674 |
| Ordinal MAE | 0.0900692841 |
| Weighted Kappa | 0.9419644636 |
| Test Loss | 0.1516360879 |

### Per-class

| Maturity | Precision | Recall | F1 |
|---|---:|---:|---:|
| 0 | 0.9673913043 | 0.9081632653 | 0.9368421053 |
| 1 | 0.8660714286 | 0.9417475728 | **0.9023255814** |
| 4 | 0.9708029197 | 0.9925373134 | 0.9815498155 |

### Confusion matrix

Rows=true, columns=predicted, class order `[0, 1, 4]`:

```text
[[178, 14,  4],
 [  6, 97,  0],
 [  0,  1,133]]
```

Observed test errors:

- M0 → M1: 14
- M0 → M4: 4
- M1 → M0: 6
- M4 → M1: 1

The weakest class is Maturity 1. Its recall is high, but precision is lower because M0 samples are frequently promoted to M1. This is the primary baseline failure mode to improve.

## 4. Reliability interpretation

This result is sufficient to mark the baseline as `REPRODUCED`, because the frozen snapshot, split assignment, checkpoint, seed, logs and final test metrics are all recorded and reproducible.

It is **not** sufficient to claim production reliability or `FIELD_VALIDATED` because:

1. The snapshot contains only Maturity 0 / 1 / 4; Maturity 2 / 3 are unresolved and absent.
2. All data are external KGCV-domain samples; Nongtori field images are not included.
3. Maturity 1 F1 is about 0.90, with clear M0↔M1 confusion.
4. The best checkpoint occurs at epoch 1 and later epochs degrade, indicating the current fine-tuning schedule needs improvement.
5. No independent field holdout has been evaluated.

Therefore this model is a **reference baseline**, not a deployment model.

## 5. Next optimization plan

Before broad Optuna search, first test a small set of high-value changes under the exact same frozen split:

1. Reduce full-model learning rate (`3e-4` → candidate `1e-4`, `5e-5`).
2. Two-stage fine tuning: classifier head warm-up with frozen backbone, then gradual unfreeze.
3. Learning-rate scheduler (cosine decay or ReduceLROnPlateau).
4. Label smoothing / focal-loss candidate only if M0↔M1 confusion persists.
5. Compare at least one stronger but efficient backbone (EfficientNet-B0 or ConvNeXt-Tiny depending runtime budget).
6. Primary selection remains validation Macro F1 with class-1 F1 and ordinal error as guardrails.
7. Do not use the frozen test split for hyperparameter selection; test is evaluated only after candidate configuration is frozen.

Promotion to `CANDIDATE` requires a repeatable improvement over this baseline without degrading critical class behavior. `FIELD_VALIDATED` remains blocked until an independent Nongtori field holdout exists.
