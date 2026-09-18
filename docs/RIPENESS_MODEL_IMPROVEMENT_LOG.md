# Nongtori Ripeness Model Improvement Log

Status: **CANONICAL / EXECUTED EVIDENCE ONLY**

이 문서는 Nongtori 숙도 모델에서 **실제로 실행된 실험 중 의사결정에 의미 있는 결과만** 기록한다. 미실행 아이디어는 `MODEL_IMPROVEMENT_STRATEGY.md`, 튜닝 후보는 `RIPENESS_TUNING_BACKLOG.md`, 기록 자격은 `MODEL_EXPERIMENT_EVIDENCE_POLICY.md`를 따른다.

---

# EXP-RIP-001 — ResNet-18 Baseline Reproduction

Status: **REPRODUCED BASELINE**

- Snapshot: `KGCV-RIPENESS-V001`
- Model: ImageNet-pretrained ResNet-18
- LR: `3e-4`
- Seed: `20260910`
- Train / Valid / Test: `2243 / 486 / 433`
- Test Macro F1: `0.9402`
- Test M1 F1: `0.9023`
- Test Ordinal MAE: `0.0901`
- Test Weighted Kappa: `0.9420`
- Primary observed failure: M0 → M1 confusion
- Validation best epoch: 1

Decision: `KEEP AS REPRODUCED BASELINE`.

---

# EXP-RIP-002 — Lower Full-Fine-Tuning LR

Status: **CONFIRMED OPTIMIZATION IMPROVEMENT / VALIDATION ONLY**

| Metric | `3e-4` | `1e-4` | `5e-5` |
|---|---:|---:|---:|
| Macro F1 | 0.9537 | 0.9696 | **0.9717** |
| M1 F1 | 0.9177 | 0.9469 | **0.9511** |
| Ordinal MAE ↓ | 0.0679 | 0.0453 | **0.0432** |
| Weighted Kappa | 0.9603 | 0.9708 | **0.9722** |

Paired confirmation on seeds `20260911/12/13`:

| Metric | `3e-4` mean ± std | `5e-5` mean ± std |
|---|---:|---:|
| Macro F1 | 0.9592 ± 0.0063 | **0.9625 ± 0.0019** |
| Ordinal MAE ↓ | 0.0487 ± 0.0059 | **0.0453 ± 0.0021** |
| Weighted Kappa | 0.9663 ± 0.0027 | **0.9709 ± 0.0016** |

Decision: `CONFIRMED — USE LR 5e-5 AS RESNET-18 FULL-FINETUNING RECIPE`.

---

# EXP-RIP-003 — Two-epoch Head-only Staged Fine-tuning

Status: **REJECTED / VALIDATION ONLY**

| Metric | Full 5e-5 | Staged 5e-5 |
|---|---:|---:|
| Macro F1 | **0.9683** | 0.9654 |
| Accuracy | **0.9691** | 0.9671 |
| Ordinal MAE ↓ | **0.0432** | 0.0494 |
| Weighted Kappa | **0.9692** | 0.9677 |

Decision: `REJECT STAGED FINE-TUNING`.

---

# EXP-RIP-004 — CosineAnnealingLR

Status: **REJECTED AFTER PAIRED 3-SEED GPU CONFIRMATION / VALIDATION ONLY**

| Metric | Constant `5e-5` mean ± std | Cosine mean ± std |
|---|---:|---:|
| Macro F1 | **0.9628 ± 0.0047** | 0.9613 ± 0.0057 |
| Accuracy | **0.9657 ± 0.0043** | 0.9636 ± 0.0063 |
| Ordinal MAE ↓ | **0.0405 ± 0.0047** | 0.0425 ± 0.0059 |
| Weighted Kappa | **0.9744 ± 0.0034** | 0.9727 ± 0.0070 |

Decision: `REJECT COSINEANNEALINGLR`.

---

# EXP-RIP-005 — Label Smoothing 0.05

Status: **REJECTED / LOCAL GPU SCREENING / VALIDATION ONLY**

| Metric | Baseline | Smoothing 0.05 |
|---|---:|---:|
| Macro F1 | **0.9683** | 0.9631 |
| Accuracy | **0.9691** | 0.9650 |
| Ordinal MAE ↓ | **0.0432** | 0.0514 |
| Weighted Kappa | **0.9692** | 0.9663 |

Decision: `REJECT LABEL_SMOOTHING=0.05`.

---

# EXP-RIP-006 — Expected Ordinal Distance Regularization

Status: **REJECTED / LOCAL GPU SCREENING / VALIDATION ONLY**

| Metric | Baseline | Ordinal-aware | Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9703** | 0.9683 | -0.0020 |
| Accuracy | **0.9712** | 0.9691 | -0.0021 |
| Ordinal MAE ↓ | **0.0412** | 0.0432 | +0.0020 |
| Weighted Kappa | **0.9707** | 0.9692 | -0.0015 |

Decision: `REJECT EXPECTED-ORDINAL-DISTANCE REGULARIZATION λ=0.20`.

---

# EXP-RIP-007 — EfficientNet-B0 Architecture

Status: **CONFIRMED ARCHITECTURE IMPROVEMENT / VALIDATION ONLY / TEST-FIELD GATE PENDING**

Initial seed `20260910` screening:

| Metric | ResNet-18 | EfficientNet-B0 | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.9683 | **0.9741** | +0.0058 |
| Accuracy | 0.9691 | **0.9753** | +0.0062 |
| Ordinal MAE ↓ | 0.0432 | **0.0309** | -0.0123 |
| Weighted Kappa | 0.9692 | **0.9781** | +0.0089 |

Paired confirmation on seeds `20260911/12/13`:

| Metric | ResNet-18 mean ± std | EfficientNet-B0 mean ± std | EfficientNet Δ |
|---|---:|---:|---:|
| Macro F1 | 0.9614 ± 0.0045 | **0.9686 ± 0.0064** | **+0.0072** |
| Accuracy | 0.9643 ± 0.0043 | **0.9698 ± 0.0063** | **+0.0055** |
| Ordinal MAE ↓ | 0.0418 ± 0.0063 | **0.0322 ± 0.0097** | **-0.0096** |
| Weighted Kappa | 0.9734 ± 0.0045 | **0.9771 ± 0.0070** | **+0.0037** |

Seed-level Macro F1 winners:
- `20260911`: ResNet-18 (`0.9662` vs `0.9618`)
- `20260912`: EfficientNet-B0 (`0.9745` vs `0.9606`)
- `20260913`: EfficientNet-B0 (`0.9696` vs `0.9574`)

Interpretation:
- the initial architecture gain reproduced in aggregate;
- EfficientNet-B0 won 2/3 paired seeds on primary Macro F1;
- all aggregate primary/ordinal metrics improved;
- stochastic variance remains non-trivial, so a single best run such as `0.9745` is not treated as the canonical expected score;
- architecture promotion does not yet equal field validation.

Decision: `CONFIRM EFFICIENTNET-B0 AS PREFERRED RIPENESS ARCHITECTURE CANDIDATE`.

Before final production/field promotion:
1. residual-error / hard-example ceiling audit;
2. resource acceptance (VRAM/runtime/params/inference cost);
3. freeze remaining tuning decisions;
4. one independent test/field gate without iterative test tuning.

---

# EXP-RIP-008 — Extended Early-Stopping Patience Diagnostic

Status: **REJECTED AS IMPROVEMENT / MEANINGFUL DIAGNOSTIC / VALIDATION ONLY**

Purpose: verify whether LR `5e-5` was being stopped prematurely because the existing `patience=5` window was too short.

Controlled setup:
- model: ResNet-18
- snapshot: `KGCV-RIPENESS-V001`
- seed: `20260910`
- LR: `5e-5`
- optimizer / augmentation / class weighting unchanged
- patience: `5 → 12`
- max epochs: `25`
- test evaluated: **NO**
- local run id: `c764f9022209`

Observed best checkpoint:

| Metric | Result |
|---|---:|
| Best epoch | **2** |
| Macro F1 | **0.9725** |
| Ordinal MAE ↓ | **0.0391** |
| Weighted Kappa | **0.9722** |

Learning behavior:
- under the old patience=5 rule, the run would have stopped at epoch 7;
- extended patience allowed observation through epoch 14;
- no epoch after 2 exceeded the epoch-2 Macro F1 `0.9725`;
- train loss continued falling from `0.1622` at epoch 2 to approximately `0.007–0.008` late in training;
- validation Macro F1 remained below the best despite continued train-loss improvement.

Interpretation:
- the evidence does **not** support the hypothesis that LR `5e-5` merely required more epochs and was being cut off too early;
- the observed pattern is more consistent with an early validation optimum followed by generalization plateau / overfitting;
- extending patience alone therefore adds training cost without producing a better validation checkpoint in this controlled ResNet run.

Scope limitation:
- this is a single-seed diagnostic on the ResNet-18 recipe;
- it is not a claim about EfficientNet-B0, field data, or production reliability.

Decision: `REJECT PATIENCE EXTENSION AS AN IMPROVEMENT`.

Do not increase patience solely to compensate for LR `5e-5`. Keep this result as diagnostic evidence and move optimization effort to evidence-backed error analysis rather than longer training.

---

# EXP-RIP-009 — Rank-Consistent Ordinal Head

Status: **REJECTED / VALIDATION ONLY / NO MULTI-SEED CONFIRMATION**

Seed `20260910`, frozen `KGCV-RIPENESS-V001`, test set not evaluated.

| Metric | EfficientNet softmax | Ordinal head |
|---|---:|---:|
| Accuracy | **0.9753** | 0.9527 |
| Macro F1 | **0.9741** | 0.9464 |
| Ordinal MAE ↓ | **0.0309** | 0.0514 |
| Weighted Kappa | **0.9781** | 0.9670 |
| M1 F1 | **0.9502** | 0.8856 |

The ordinal head reduced M0→M1 false positives but collapsed M1 recall (`0.9459 → 0.8018`) and regressed the primary/supporting metrics.

Decision: `REJECT CURRENT ORDERED-CUMULATIVE ORDINAL HEAD`.

Do not run paired confirmation or rescue tuning for this formulation. Preserve as negative evidence that this specific ordinal-head design does not improve the current frozen benchmark.

Detailed result: `docs/experiments/ripeness/EXP-RIP-009_ORDINAL_HEAD_RESULT.md`.

---

# Current preferred recipe

```text
Architecture : ImageNet-pretrained EfficientNet-B0 (preferred candidate)
Training     : full fine-tuning from epoch 1
Base LR      : constant 5e-5 (controlled comparison recipe; EfficientNet-specific tuning not yet performed)
Optimizer    : AdamW
Loss         : weighted CrossEntropy, label_smoothing=0
Selection    : validation Macro F1
Data         : KGCV-RIPENESS-V001 frozen snapshot / shared immutable cache
Test usage   : closed during optimization
Status       : validation-confirmed architecture candidate; test/field gate pending
```

Confirmed changes:
- lower full-fine-tuning LR (`5e-5`) for the ResNet optimization baseline;
- EfficientNet-B0 architecture advantage under the controlled recipe.

Rejected branches:
- 2-epoch head-only staged warm-up;
- CosineAnnealingLR (`eta_min=5e-6`, `T_max=15`);
- label smoothing `0.05`;
- expected ordinal-distance regularizer `λ=0.20`;
- extending ResNet early-stopping patience from `5` to `12` as a remedy for LR `5e-5`.

Next action is not blind tuning toward `0.98`. Follow `RIPENESS_TUNING_BACKLOG.md`: residual-error audit first, then only evidence-triggered tuning.
