# EXP-RIP-004 — Cosine Scheduler Screening

Status: **REJECTED / MULTI-SEED GPU CONFIRMATION / VALIDATION ONLY**

## Evidence

- Task: ripeness / maturity ordinal classification
- Execution: local CUDA GPU
- GPU: NVIDIA GeForce RTX 4060 8GB
- PyTorch: `2.5.1+cu121`
- CUDA runtime: `12.1`
- Snapshot: `KGCV-RIPENESS-V001`
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

## Observed Problem

EXP-RIP-002 established `5e-5` as the current ResNet-18 full-fine-tuning LR, but validation performance still saturated while train loss continued to decline.

EXP-RIP-003 rejected staged head-only warm-up, so scheduler behavior was tested as the next isolated optimization mechanism.

## Hypothesis

A smooth cosine LR decay from the confirmed base LR could reduce late-epoch over-optimization and improve validation generalization without changing the model, data, augmentation, loss, optimizer, or starting LR.

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

Only scheduler behavior changed.

---

## Initial Screening — seed 20260910

| Metric | Constant LR | Cosine | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.9683 | **0.9703** | +0.0020 |
| Accuracy | 0.9691 | **0.9712** | +0.0021 |
| Ordinal MAE ↓ | 0.0432 | **0.0412** | -0.0020 |
| Weighted Kappa | 0.9692 | **0.9707** | +0.0015 |
| Best epoch | 2 | 2 | 0 |

This was directionally positive but too small to promote without confirmation.

Decision after screening: `PROMOTE TO PAIRED 3-SEED CONFIRMATION ONLY`.

---

## Paired 3-seed GPU Confirmation

Seeds:

- `20260911`
- `20260912`
- `20260913`

### Seed 20260911

| Metric | Constant | Cosine | Winner |
|---|---:|---:|---|
| Macro F1 | **0.9662** | 0.9624 | Constant |
| Accuracy | **0.9691** | 0.9650 | Constant |
| Ordinal MAE ↓ | **0.0350** | 0.0391 | Constant |
| Weighted Kappa | **0.9783** | 0.9753 | Constant |
| Best epoch | 10 | 7 | — |

### Seed 20260912

| Metric | Constant | Cosine | Winner |
|---|---:|---:|---|
| Macro F1 | 0.9647 | **0.9664** | Cosine |
| Accuracy | 0.9671 | **0.9691** | Cosine |
| Ordinal MAE ↓ | 0.0432 | **0.0391** | Cosine |
| Weighted Kappa | 0.9723 | **0.9781** | Cosine |
| Best epoch | 8 | 13 | — |

### Seed 20260913

| Metric | Constant | Cosine | Winner |
|---|---:|---:|---|
| Macro F1 | **0.9574** | 0.9551 | Constant |
| Accuracy | **0.9609** | 0.9568 | Constant |
| Ordinal MAE ↓ | **0.0432** | 0.0494 | Constant |
| Weighted Kappa | **0.9725** | 0.9648 | Constant |
| Best epoch | 7 | 5 | — |

### 3-seed aggregate

| Metric | Constant `5e-5` mean ± std | Cosine mean ± std | Mean Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9628 ± 0.0047** | 0.9613 ± 0.0057 | **-0.0015** |
| Accuracy | **0.9657 ± 0.0043** | 0.9636 ± 0.0063 | **-0.0021** |
| Ordinal MAE ↓ | **0.0405 ± 0.0047** | 0.0425 ± 0.0059 | **+0.0021** |
| Weighted Kappa | **0.9744 ± 0.0034** | 0.9727 ± 0.0070 | **-0.0016** |

Cosine won one seed but lost two. Across the three confirmation seeds, every aggregate metric moved slightly in the wrong direction, and variance also increased.

## Interpretation

The initial positive screening did not reproduce.

This is exactly why the single-seed result was not promoted prematurely: the apparent gain at seed `20260910` was not stable across additional seeds.

The scheduler changed the optimization trajectory — for example, seed `20260912` reached its best cosine checkpoint at epoch 13 — but later convergence did not translate into reliable aggregate improvement.

No evidence justifies further tuning of `eta_min`, `T_max`, or adjacent cosine parameters under the current recipe.

## Decision

`REJECT COSINEANNEALINGLR FOR CURRENT RESNET-18 RECIPE`

Keep the simpler confirmed recipe:

```text
ResNet-18
full fine-tuning from epoch 1
AdamW
constant LR = 5e-5
selection = validation Macro F1
```

Do not continue scheduler micro-tuning based on this result. The next improvement experiment should move to a genuinely different mechanism.

## Reliability / Scope

- actual local GPU execution: YES
- frozen snapshot: YES
- same validation split: YES
- controlled variable isolation: YES
- initial screening: YES
- paired 3-seed confirmation: YES
- test tuning: NO
- field validation: NO
- production claim: NO

The confirmation run completed successfully with no model errors. Dataset-cache inefficiency observed during this run is an execution-infrastructure concern and is tracked separately from model evidence.
