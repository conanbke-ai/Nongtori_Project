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

Controlled change:

```text
Current:   full backbone from epoch 1, LR 5e-5
Candidate: head-only epoch 1-2 → full backbone from epoch 3, LR 5e-5
```

Actual local GPU result:

| Metric | Full 5e-5 | Staged 5e-5 | Staged Δ |
|---|---:|---:|---:|
| Macro F1 | **0.9683** | 0.9654 | -0.0029 |
| Accuracy | **0.9691** | 0.9671 | -0.0020 |
| Ordinal MAE ↓ | **0.0432** | 0.0494 | +0.0062 |
| Weighted Kappa | **0.9692** | 0.9677 | -0.0015 |
| Best epoch | 2 | 8 | +6 |

Decision: `REJECT STAGED FINE-TUNING FOR CURRENT RESNET-18 RECIPE`.

The staged recipe changed the optimization trajectory but did not improve the primary metric. Do not repeatedly retune warm-up length.

---

# EXP-RIP-004 — CosineAnnealingLR

Status: **REJECTED AFTER PAIRED 3-SEED GPU CONFIRMATION / VALIDATION ONLY**

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-004_COSINE_SCHEDULER.md`

## Hypothesis tested

After LR `5e-5` was confirmed and staged warm-up was rejected, test whether cosine LR decay improves generalization while keeping model, data, optimizer, augmentation, starting LR and selection rule fixed.

## Initial screening

Seed `20260910` was directionally positive:

| Metric | Constant 5e-5 | Cosine | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.9683 | **0.9703** | +0.0020 |
| Accuracy | 0.9691 | **0.9712** | +0.0021 |
| Ordinal MAE ↓ | 0.0432 | **0.0412** | -0.0020 |
| Weighted Kappa | 0.9692 | **0.9707** | +0.0015 |

Because the effect was small, it was not promoted and instead advanced to paired multi-seed confirmation.

## Paired confirmation — seeds 20260911/12/13

Seed-level primary results:

| Seed | Constant Macro F1 | Cosine Macro F1 | Winner |
|---|---:|---:|---|
| 20260911 | **0.9662** | 0.9624 | Constant |
| 20260912 | 0.9647 | **0.9664** | Cosine |
| 20260913 | **0.9574** | 0.9551 | Constant |

Aggregate:

| Metric | Constant `5e-5` mean ± std | Cosine mean ± std | Mean Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9628 ± 0.0047** | 0.9613 ± 0.0057 | -0.0015 |
| Accuracy | **0.9657 ± 0.0043** | 0.9636 ± 0.0063 | -0.0021 |
| Ordinal MAE ↓ | **0.0405 ± 0.0047** | 0.0425 ± 0.0059 | +0.0021 |
| Weighted Kappa | **0.9744 ± 0.0034** | 0.9727 ± 0.0070 | -0.0016 |

The initial positive screening did not reproduce. Cosine won only one of three confirmation seeds, aggregate performance was slightly worse on every reported metric, and variance increased.

## Decision

`REJECT COSINEANNEALINGLR FOR CURRENT RESNET-18 RECIPE`

Do not micro-tune `eta_min`, `T_max`, or neighboring cosine settings. The experiment has already produced decision-changing evidence.

---

# Current confirmed recipe

```text
Model      : ImageNet-pretrained ResNet-18
Training   : full fine-tuning from epoch 1
Base LR    : constant 5e-5
Optimizer  : AdamW
Selection  : validation Macro F1
Test usage : closed during optimization
```

Confirmed optimization changes:
- lower full-fine-tuning LR (`5e-5`)

Rejected optimization branches:
- 2-epoch head-only staged warm-up
- CosineAnnealingLR (`eta_min=5e-6`, `T_max=15`)

Next experiments must move to a genuinely different evidence-backed mechanism rather than repeating LR, warm-up, or cosine-scheduler variations.
