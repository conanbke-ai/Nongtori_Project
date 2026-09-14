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

The baseline established the reproducible comparison point and showed that M1 boundary behavior and very early validation saturation were the first useful optimization targets.

---

# EXP-RIP-002 — Lower Full-Fine-Tuning LR

Status: **CONFIRMED OPTIMIZATION IMPROVEMENT / VALIDATION ONLY**

## Actual evidence

Initial controlled screening compared only LR while keeping snapshot, split, model, augmentation, optimizer family, class weighting and checkpoint rule fixed.

| Metric | `3e-4` | `1e-4` | `5e-5` |
|---|---:|---:|---:|
| Macro F1 | 0.9537 | 0.9696 | **0.9717** |
| M1 F1 | 0.9177 | 0.9469 | **0.9511** |
| Ordinal MAE ↓ | 0.0679 | 0.0453 | **0.0432** |
| Weighted Kappa | 0.9603 | 0.9708 | **0.9722** |

The target failure pattern also improved (`M0 → M1: 12 → 7`).

Paired confirmation on seeds `20260911/12/13` showed:

| Metric | `3e-4` mean ± std | `5e-5` mean ± std |
|---|---:|---:|
| Macro F1 | 0.9592 ± 0.0063 | **0.9625 ± 0.0019** |
| Ordinal MAE ↓ | 0.0487 ± 0.0059 | **0.0453 ± 0.0021** |
| Weighted Kappa | 0.9663 ± 0.0027 | **0.9709 ± 0.0016** |

`5e-5` did not win every metric on every seed, but improved the aggregate and substantially reduced seed variance.

Decision: `CONFIRMED — USE LR 5e-5 AS CURRENT RESNET-18 FULL-FINETUNING RECIPE`.

No further fine-grained LR sweep is justified.

---

# EXP-RIP-003 — Two-epoch Head-only Staged Fine-tuning

Status: **REJECTED / MEANINGFUL GPU EVIDENCE / VALIDATION ONLY**

Detailed evidence: `docs/experiments/ripeness/EXP-RIP-003_STAGED_FINETUNING.md`

## Observed problem

Even after LR `5e-5` was confirmed, train loss continued to fall rapidly while validation performance saturated early.

## Hypothesis tested

Head-only training for epochs 1-2 followed by full backbone unfreeze could preserve pretrained features and improve generalization.

## Controlled change

Only the trainable-parameter schedule changed.

```text
Current:   full backbone from epoch 1, LR 5e-5
Candidate: head-only epoch 1-2 → full backbone from epoch 3, LR 5e-5
```

The test set remained closed.

## Actual local GPU result

Execution environment:
- NVIDIA GeForce RTX 4060 8GB
- PyTorch `2.5.1+cu121`
- CUDA runtime `12.1`
- seed `20260910`
- structured run id `35c5b0b463fd`

| Metric | Full 5e-5 | Staged 5e-5 | Staged Δ |
|---|---:|---:|---:|
| Macro F1 | **0.9683** | 0.9654 | -0.0029 |
| Accuracy | **0.9691** | 0.9671 | -0.0020 |
| Ordinal MAE ↓ | **0.0432** | 0.0494 | +0.0062 |
| Weighted Kappa | **0.9692** | 0.9677 | -0.0015 |
| Best epoch | 2 | 8 | +6 |

Staged training changed the optimization trajectory and delayed the best epoch, but it did not improve the primary validation metric. A staged epoch reached a slightly higher Kappa (`0.9707` at epoch 6), but that checkpoint had lower Macro F1 (`0.9631`) and therefore did not constitute a superior overall candidate.

The first two head-only epochs were also weak (`Macro F1 0.4660 → 0.5672`). Performance recovered immediately after backbone unfreeze, but never exceeded the simpler full-fine-tuning recipe.

## Decision

`REJECT STAGED FINE-TUNING FOR CURRENT RESNET-18 RECIPE`

Keep:

```text
ResNet-18
full fine-tuning from epoch 1
LR 5e-5
```

Do not repeatedly retune warm-up length. This experiment already changed the decision by ruling out the staged-warm-up branch.

The earlier Windows DataLoader multiprocessing error is excluded from this model-improvement record because it was an execution-environment compatibility issue rather than model evidence.

---

# Current confirmed recipe

```text
Model      : ImageNet-pretrained ResNet-18
Training   : full fine-tuning from epoch 1
Base LR    : 5e-5
Optimizer  : AdamW
Selection  : validation Macro F1
Test usage : closed during optimization
```

Next experiments must move to a genuinely different evidence-backed axis rather than repeating LR or warm-up variations.
