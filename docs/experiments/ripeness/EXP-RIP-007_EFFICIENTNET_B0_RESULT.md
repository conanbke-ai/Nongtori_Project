# EXP-RIP-007 — EfficientNet-B0 Architecture Result

Status: **CONFIRMED ARCHITECTURE IMPROVEMENT / VALIDATION ONLY / TEST-FIELD GATE PENDING**

## Purpose

After V003–V006 failed to improve the confirmed ResNet-18 recipe, V007 tested whether changing representation architecture was more valuable than continuing optimizer/loss micro-tuning.

The controlled change was:

- baseline: ImageNet-pretrained ResNet-18
- candidate: ImageNet-pretrained EfficientNet-B0

The frozen snapshot, split, augmentation, input size, weighted CrossEntropy, AdamW, constant LR `5e-5`, full fine-tuning, batch size, validation-based checkpoint selection, and test-set closure were held constant.

## Screening evidence

Run `adc9e50ee7f0`, seed `20260910`, RTX 4060, shared immutable cache reused.

| Metric | ResNet-18 | EfficientNet-B0 | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.9683 | **0.9741** | **+0.0058** |
| Accuracy | 0.9691 | **0.9753** | **+0.0062** |
| Ordinal MAE ↓ | 0.0432 | **0.0309** | **-0.0123** |
| Weighted Kappa | 0.9692 | **0.9781** | **+0.0089** |

This was treated only as positive screening and promoted to paired multi-seed confirmation.

## Paired 3-seed confirmation

Seeds: `20260911 / 20260912 / 20260913`.

### Seed-level best validation checkpoints

| Seed | Backbone | Macro F1 | Accuracy | Ordinal MAE ↓ | Weighted Kappa |
|---|---|---:|---:|---:|---:|
| 20260911 | ResNet-18 | **0.9662** | **0.9691** | **0.0350** | **0.9783** |
| 20260911 | EfficientNet-B0 | 0.9618 | 0.9630 | 0.0432 | 0.9692 |
| 20260912 | ResNet-18 | 0.9606 | 0.9630 | 0.0473 | 0.9694 |
| 20260912 | EfficientNet-B0 | **0.9745** | **0.9753** | **0.0247** | **0.9824** |
| 20260913 | ResNet-18 | 0.9574 | 0.9609 | 0.0432 | 0.9725 |
| 20260913 | EfficientNet-B0 | **0.9696** | **0.9712** | **0.0288** | **0.9796** |

EfficientNet-B0 won Macro F1 on **2/3 paired seeds**.

### Aggregate result

| Metric | ResNet-18 mean ± std | EfficientNet-B0 mean ± std | EfficientNet Δ |
|---|---:|---:|---:|
| Macro F1 | 0.9614 ± 0.0045 | **0.9686 ± 0.0064** | **+0.0072** |
| Accuracy | 0.9643 ± 0.0043 | **0.9698 ± 0.0063** | **+0.0055** |
| Ordinal MAE ↓ | 0.0418 ± 0.0063 | **0.0322 ± 0.0097** | **-0.0096** |
| Weighted Kappa | 0.9734 ± 0.0045 | **0.9771 ± 0.0070** | **+0.0037** |

The candidate improved every aggregate primary/supporting metric, though its cross-seed variance was somewhat larger.

## V008 follow-up evidence

A paired validation error audit on seed `20260912` showed:

- validation samples: 486
- EfficientNet errors: 12
- ResNet errors: 18
- both correct: 464
- EfficientNet-only correct: 10
- ResNet-only correct: 4
- shared same error: 8
- EfficientNet residual transitions: `M0→M1 = 10`, `M1→M0 = 2`, `M4 errors = 0`

This established that the remaining error on the current benchmark is concentrated at the M0/M1 boundary rather than spread broadly across maturity classes.

## Decision

`PROMOTE EFFICIENTNET-B0 TO PREFERRED DEVELOPMENT-BENCHMARK ARCHITECTURE CANDIDATE`

This does **not** mean production promotion or field validation.

The current `KGCV-RIPENESS-V001` line is now frozen as a development benchmark because field/photo/video data and final field annotation criteria are still being organized. Generic additional tuning is paused until a successor data/label snapshot is frozen.

See:

- `docs/RIPENESS_BENCHMARK_FREEZE_20260915.md`
- `docs/RIPENESS_DATA_LABEL_BACKLOG.md`
- `docs/RIPENESS_TUNING_BACKLOG.md`

## Re-open gate

Before further ripeness optimization:

1. organize representative real photo/video data;
2. version final Maturity 0–4 annotation criteria;
3. decide flower / fruit-set / NOT_APPLICABLE treatment;
4. define video/group duplicate and leakage policy;
5. freeze a new normalized immutable snapshot;
6. re-run a clean baseline on that successor snapshot.

## Literature basis

Architecture selection was motivated by Tan & Le, *EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks* (ICML 2019). The paper is used only as hypothesis/design basis; all metrics above are Nongtori project evidence.

## Portfolio significance

V007 demonstrates the complete decision path:

`optimization plateau → literature-grounded architecture hypothesis → controlled screening → paired multi-seed confirmation → residual-error audit → evidence-based benchmark freeze`.
