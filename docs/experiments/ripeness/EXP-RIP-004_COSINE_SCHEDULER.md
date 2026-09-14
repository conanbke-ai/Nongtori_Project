# EXP-RIP-004 — Cosine Scheduler Screening

Status: **POSITIVE SCREENING / CONFIRMATION REQUIRED / VALIDATION ONLY**

## Evidence

- Task: ripeness / maturity ordinal classification
- Execution: local CUDA GPU
- GPU: NVIDIA GeForce RTX 4060 8GB
- PyTorch: `2.5.1+cu121`
- CUDA runtime: `12.1`
- Snapshot: `KGCV-RIPENESS-V001`
- Seed: `20260910`
- Test evaluated: **NO**
- Change category: `OPTIMIZATION`
- Controlled change: scheduler only
- Model: ImageNet-pretrained ResNet-18
- Fine tuning: full backbone from epoch 1
- Optimizer: AdamW
- Base LR: `5e-5`
- Weight decay: `1e-4`
- Batch size: 32
- Candidate scheduler: `CosineAnnealingLR`
- `eta_min`: `5e-6`
- `T_max`: 15
- Structured run id: `39ed7be9efc8`
- Successful run duration: about `13:05`

## Observed Problem

EXP-RIP-002 established `5e-5` as the current ResNet-18 full-fine-tuning LR, but the best validation checkpoint still appears very early and subsequent epochs do not consistently improve generalization.

EXP-RIP-003 showed that staged head-only warm-up did not improve the primary metric, so the next controlled optimization mechanism was scheduler behavior.

## Hypothesis

A smooth reduction from the confirmed base LR could reduce late-epoch over-optimization and improve validation generalization without changing the model, data, augmentation, loss, or initial LR.

## Controlled Comparison

### Baseline

```text
ResNet-18
full fine-tuning from epoch 1
AdamW
constant LR = 5e-5
```

### Candidate

```text
ResNet-18
full fine-tuning from epoch 1
AdamW
CosineAnnealingLR
start LR = 5e-5
eta_min = 5e-6
T_max = 15
```

Only scheduler behavior changes.

## Actual Screening Result

| Metric | Constant LR | Cosine | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.9683 | **0.9703** | **+0.0020** |
| Accuracy | 0.9691 | **0.9712** | **+0.0021** |
| Ordinal MAE ↓ | 0.0432 | **0.0412** | **-0.0020** |
| Weighted Kappa | 0.9692 | **0.9707** | **+0.0015** |
| Best epoch | 2 | 2 | 0 |

Both models selected epoch 2 as the best Macro-F1 checkpoint.

## Interpretation

This result is directionally positive because all major validation metrics moved in the same favorable direction.

However, the magnitude is small. Macro F1 improved by only about 0.2 percentage points, and the best epoch did not move later. Therefore the screening result does **not** establish that cosine scheduling materially improves the model.

The candidate is worth confirming because:

1. the only controlled change was scheduler behavior;
2. Macro F1, Accuracy, Ordinal MAE and Weighted Kappa all improved together;
3. no critical metric regressed at the selected checkpoint.

But because this is a single seed and the delta is small, it must not be promoted from screening evidence to a confirmed recipe without paired multi-seed evidence.

## Decision

`PROMOTE TO PAIRED 3-SEED CONFIRMATION ONLY`

Do not:
- tune `eta_min` repeatedly;
- compare multiple scheduler families yet;
- open the frozen test set;
- describe cosine as an improvement before confirmation.

Next step:

```text
Seeds 20260911 / 20260912 / 20260913
Constant 5e-5 vs Cosine 5e-5
same frozen validation split
→ aggregate mean ± std
→ KEEP or REJECT
```

If the mean improvement is not reproduced, or variance worsens without a meaningful gain, reject scheduler use and move to a different improvement axis.

## Reliability / Scope

- actual GPU execution: YES
- frozen snapshot: YES
- controlled variable isolation: YES
- test tuning: NO
- single-seed evidence: YES
- multi-seed confirmation: NO
- field validation: NO
