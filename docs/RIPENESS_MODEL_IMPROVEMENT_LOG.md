# Nongtori Ripeness Model Improvement Log

Status: **CANONICAL / EXECUTED EVIDENCE ONLY**

이 문서는 Nongtori 숙도 모델에서 **실제로 실행된 실험 중 의사결정에 의미 있는 결과만** 기록한다. 미실행 아이디어는 `MODEL_IMPROVEMENT_STRATEGY.md`, 기록 자격은 `MODEL_EXPERIMENT_EVIDENCE_POLICY.md`를 따른다.

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

Decision: `CONFIRMED — USE LR 5e-5 AS CURRENT RESNET-18 FULL-FINETUNING RECIPE`.

---

# EXP-RIP-003 — Two-epoch Head-only Staged Fine-tuning

Status: **REJECTED / VALIDATION ONLY**

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-003_STAGED_FINETUNING.md`

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

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-004_COSINE_SCHEDULER.md`

Initial screening was slightly positive, but paired confirmation on seeds `20260911/12/13` did not reproduce the gain.

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

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-005_LABEL_SMOOTHING.md`

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

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-006_ORDINAL_LOSS.md`

Controlled change:

```text
Baseline  : weighted CrossEntropy
Candidate : weighted CrossEntropy + 0.20 × expected normalized maturity distance
Values    : [0, 1, 4]
```

Actual local GPU paired screening (`RTX 4060`, seed `20260910`, run `a62b466f71e3`):

| Metric | Baseline | Ordinal-aware | Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9703** | 0.9683 | -0.0020 |
| Accuracy | **0.9712** | 0.9691 | -0.0021 |
| Ordinal MAE ↓ | **0.0412** | 0.0432 | +0.0020 |
| Weighted Kappa | **0.9707** | 0.9692 | -0.0015 |
| Best epoch | 2 | 2 | 0 |

The candidate failed to improve the ordinal-sensitive metrics it explicitly targeted. No lambda micro-sweep is justified.

Decision: `REJECT EXPECTED-ORDINAL-DISTANCE REGULARIZATION λ=0.20`.

Reproducibility note: exact same-seed scores show small variation across separate CUDA runs because deterministic algorithms are not currently enforced. V006 is interpreted as a same-run paired screening result; future confirmation/acceptance must explicitly account for stochastic variance.

---

# Current confirmed recipe

```text
Model      : ImageNet-pretrained ResNet-18
Training   : full fine-tuning from epoch 1
Base LR    : constant 5e-5
Optimizer  : AdamW
Loss       : weighted CrossEntropy, label_smoothing=0
Selection  : validation Macro F1
Test usage : closed during optimization
```

Confirmed changes:
- lower full-fine-tuning LR (`5e-5`)

Rejected branches:
- 2-epoch head-only staged warm-up
- CosineAnnealingLR (`eta_min=5e-6`, `T_max=15`)
- label smoothing `0.05`
- expected ordinal-distance regularizer `λ=0.20`

Next experiments should move away from LR/scheduler/warm-up/small loss-coefficient tuning. Architecture/backbone comparison is now the preferred next axis unless a genuinely different ordinal formulation is justified.
