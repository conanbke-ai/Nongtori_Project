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

No further fine-grained LR sweep is justified.

---

# EXP-RIP-003 — Two-epoch Head-only Staged Fine-tuning

Status: **REJECTED / MEANINGFUL GPU EVIDENCE / VALIDATION ONLY**

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-003_STAGED_FINETUNING.md`

| Metric | Full 5e-5 | Staged 5e-5 | Staged Δ |
|---|---:|---:|---:|
| Macro F1 | **0.9683** | 0.9654 | -0.0029 |
| Accuracy | **0.9691** | 0.9671 | -0.0020 |
| Ordinal MAE ↓ | **0.0432** | 0.0494 | +0.0062 |
| Weighted Kappa | **0.9692** | 0.9677 | -0.0015 |
| Best epoch | 2 | 8 | +6 |

Decision: `REJECT STAGED FINE-TUNING FOR CURRENT RESNET-18 RECIPE`.

---

# EXP-RIP-004 — CosineAnnealingLR

Status: **REJECTED AFTER PAIRED 3-SEED GPU CONFIRMATION / VALIDATION ONLY**

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-004_COSINE_SCHEDULER.md`

Initial seed `20260910` screening was slightly positive, but paired confirmation on seeds `20260911/12/13` did not reproduce the gain.

| Metric | Constant `5e-5` mean ± std | Cosine mean ± std | Mean Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9628 ± 0.0047** | 0.9613 ± 0.0057 | -0.0015 |
| Accuracy | **0.9657 ± 0.0043** | 0.9636 ± 0.0063 | -0.0021 |
| Ordinal MAE ↓ | **0.0405 ± 0.0047** | 0.0425 ± 0.0059 | +0.0021 |
| Weighted Kappa | **0.9744 ± 0.0034** | 0.9727 ± 0.0070 | -0.0016 |

Decision: `REJECT COSINEANNEALINGLR FOR CURRENT RESNET-18 RECIPE`.

Do not micro-tune `eta_min`, `T_max`, or neighboring cosine settings.

---

# EXP-RIP-005 — Label Smoothing 0.05

Status: **REJECTED / LOCAL GPU SCREENING / VALIDATION ONLY**

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-005_LABEL_SMOOTHING.md`

## Hypothesis tested

After exhausting the first optimization axes, test whether mild label smoothing reduces over-confident adjacent maturity-boundary decisions.

Only the loss smoothing parameter changed:

```text
Baseline  : weighted CrossEntropy, label_smoothing=0
Candidate : weighted CrossEntropy, label_smoothing=0.05
```

Actual local GPU screening (`RTX 4060`, seed `20260910`, run `bc8ce459c1b6`):

| Metric | Baseline | Smoothing 0.05 | Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9683** | 0.9631 | -0.0052 |
| Accuracy | **0.9691** | 0.9650 | -0.0041 |
| Ordinal MAE ↓ | **0.0432** | 0.0514 | +0.0082 |
| Weighted Kappa | **0.9692** | 0.9663 | -0.0029 |
| Best epoch | 2 | 6 | +4 |

The candidate delayed the best epoch but degraded every reported primary/ordinal metric. Raw CE loss values are not compared across the two objectives because smoothing changes the target distribution and therefore the loss scale.

Decision: `REJECT LABEL_SMOOTHING=0.05 FOR CURRENT RESNET-18 RECIPE`.

Do not micro-sweep neighboring smoothing values. Move to a genuinely different loss mechanism if continuing the LOSS axis.

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

Next experiments must move to a genuinely different evidence-backed mechanism rather than repeating LR, warm-up, cosine, or label-smoothing micro-variations.
