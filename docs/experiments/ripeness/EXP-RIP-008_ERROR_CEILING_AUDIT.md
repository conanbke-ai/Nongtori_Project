# EXP-RIP-008 — Validation Residual Error / Ceiling Audit

Status: **AUDIT COMPLETE / DATA-BOUNDARY REVIEW REQUIRED / VALIDATION ONLY**
Date: **2026-09-15**

## Purpose

After EfficientNet-B0 was confirmed as the preferred validation architecture candidate, this audit asked whether the remaining error is broad model failure or concentrated in a narrow maturity boundary / data ambiguity region.

No training or test-set evaluation was performed. Two paired V007 validation checkpoints were run over the same frozen 486-sample validation set.

## Actual result

| Metric | ResNet-18 | EfficientNet-B0 |
|---|---:|---:|
| Accuracy | 0.9630 | **0.9753** |
| Macro F1 | 0.9606 | **0.9745** |
| Ordinal MAE ↓ | 0.0473 | **0.0247** |
| Weighted Kappa | 0.9694 | **0.9824** |
| Error count | 18 | **12** |

### Error overlap

| Bucket | Samples |
|---|---:|
| Both correct | 464 |
| EfficientNet only correct | 10 |
| ResNet only correct | 4 |
| Shared same error | **8** |
| Shared different error | **0** |

EfficientNet corrected 10 errors that ResNet made while introducing 4 errors that ResNet avoided. Eight samples were misclassified identically by both architectures.

### EfficientNet residual confusion

| True → Predicted | Count |
|---|---:|
| M0 → M1 | **10** |
| M1 → M0 | **2** |
| Any error involving M4 | **0** |

EfficientNet confusion matrix:

```text
true M0: 240  10   0
true M1:   2 109   0
true M4:   0   0 125
```

Per-class F1:

- M0: `0.9756`
- M1: `0.9478`
- M4: `1.0000`

## Interpretation

The residual error is **not distributed across the maturity space**. All 12 EfficientNet errors are confined to the adjacent `M0 ↔ M1` boundary, and 10/12 are the asymmetric `M0 → M1` direction.

This materially changes the tuning strategy:

1. There is no current evidence that M4 representation needs further tuning.
2. A generic global architecture/optimizer/loss sweep would spend most capacity on regions that are already solved on this validation set.
3. Eight of the 12 EfficientNet errors (`66.7%`) are shared same-direction errors with ResNet, which raises the probability of a common data/label/crop/domain boundary rather than an architecture-specific defect.
4. The four `RESNET_ONLY_CORRECT` samples show that EfficientNet is not strictly dominant sample-by-sample, so complementary errors exist, but the set is too small to justify an ensemble without resource/field evidence.
5. Accuracy `0.98` on 486 samples requires at most 9 errors. The current EfficientNet checkpoint has 12 errors, so only three corrected samples separate `0.9753` from `>=0.98`. This is too small a count to justify blind tuning against a headline threshold.

## Decision

`DO NOT START GENERIC HYPERPARAMETER TUNING.`

Promote the next work item to **M0/M1 boundary review**.

The 12 EfficientNet residual errors, especially the eight shared same errors, must be reviewed against the original crop/source context and assigned one of:

- `LABEL_AMBIGUITY`
- `CROP_QUALITY`
- `DOMAIN_VARIATION`
- `LIKELY_MODEL_LIMIT`
- `REVIEW_REQUIRED`

`MODEL_DISAGREEMENT` remains useful for the 14 samples where only one architecture is correct.

## Conditional next experiment

Only after manual/data-context review:

- if errors cluster by lighting/viewpoint/occlusion → targeted augmentation experiment;
- if labels are ambiguous/inconsistent → label adjudication / boundary-definition work before model tuning;
- if clean labels and clean crops remain consistently hard → boundary-aware or structurally ordinal formulation;
- if errors are architecture-specific and operational cost allows → architecture follow-up;
- if models have sufficiently complementary clean-label errors → evaluate ensemble value against inference cost, not before.

## Portfolio significance

This audit converts a vague question — “why is validation not yet 0.98?” — into an evidence-based diagnosis: the remaining error is a small, highly localized M0/M1 boundary problem. The next engineering action is therefore selected from residual-error evidence rather than from arbitrary hyperparameter search.
