# Nongtori Ripeness Tuning Backlog

Status: **PAUSED AFTER V008 / DATA-LABEL FREEZE REQUIRED BEFORE NEXT TRAINING**
Updated: **2026-09-15 — benchmark frozen after V008**

## Purpose

This backlog separates **things worth investigating** from **things already tested and rejected**. It exists to prevent repeated parameter tweaking and to keep the improvement path evidence-driven.

A backlog item is not permission to run a grid search. Before execution it must have observed project evidence, literature/technical basis where applicable, one clear hypothesis, controlled variables, and acceptance/rejection criteria.

## Current evidence

### V007 — architecture confirmation

EfficientNet-B0 improved aggregate validation performance over ResNet-18 across paired seeds `20260911/12/13`:

| Metric | ResNet-18 mean ± std | EfficientNet-B0 mean ± std | EfficientNet Δ |
|---|---:|---:|---:|
| Macro F1 | 0.9614 ± 0.0045 | **0.9686 ± 0.0064** | **+0.0072** |
| Accuracy | 0.9643 ± 0.0043 | **0.9698 ± 0.0063** | **+0.0055** |
| Ordinal MAE ↓ | 0.0418 ± 0.0063 | **0.0322 ± 0.0097** | **-0.0096** |
| Weighted Kappa | 0.9734 ± 0.0045 | **0.9771 ± 0.0070** | **+0.0037** |

### V008 — residual error audit

Selected paired checkpoint audit on 486 validation samples:

- EfficientNet errors: **12**
- ResNet errors: 18
- both correct: 464
- EfficientNet-only correct: 10
- ResNet-only correct: 4
- shared same error: **8**
- EfficientNet residual transitions: **M0→M1 = 10, M1→M0 = 2, M4 errors = 0**
- EfficientNet M1 F1: `0.9478`
- EfficientNet M4 F1: `1.0000`

Conclusion: the current residual problem is highly localized at the **M0/M1 boundary**, not a broad maturity-classification failure.

## Benchmark freeze decision

The current photo/video/field inventory is still being organized, and part of the present material is explicitly development/testing data. Therefore V001–V008 are frozen as a **development benchmark line**, not as final field-model optimization.

See:

- `RIPENESS_BENCHMARK_FREEZE_20260915.md`
- `RIPENESS_DATA_LABEL_BACKLOG.md`
- `LABEL_MAPPING_POLICY.md`

### Why tuning is paused

1. the future field dataset distribution is not frozen;
2. the final field annotation guideline is not frozen;
3. external benchmark mapping and final field visual criteria are intentionally separated;
4. further score chasing on the current 486 validation samples may optimize a temporary benchmark;
5. the model already provides sufficient evidence to retain EfficientNet-B0 as the current preferred benchmark candidate.

Accordingly **do not launch V009 training yet**.

## Re-open conditions

At least the following must be materially complete before a new ripeness optimization experiment is promoted:

- representative real photo/video data organized;
- flower / fruit-set / NOT_APPLICABLE handling decided;
- Maturity 0–4 annotation criteria versioned;
- M0/M1 ambiguous-boundary rule defined;
- video/frame grouping and duplicate policy defined;
- adjudication workflow defined;
- new normalized immutable snapshot frozen;
- leakage-safe split regenerated for that snapshot.

Then run a clean baseline on the new snapshot before deciding which historical tuning choices should be reused.

## Deferred experiment candidates

These remain candidates only, not active work:

### Targeted augmentation
Use only if the new field dataset shows repeated illumination, exposure, occlusion, framing, scale, or viewpoint errors.

### M0/M1 boundary formulation
Use only if final labels/crops are clean and an adjacent-stage model error remains. Possible directions include structural ordinal classification, boundary-aware/cost-sensitive objectives, or uncertainty/abstention.

### Architecture follow-up
ConvNeXt-Tiny remains available if future representation evidence or operational constraints justify comparison. Do not run an architecture tournament simply to chase `0.98`.

### EfficientNet-specific optimization
Architecture-specific LR, discriminative LR/layer-wise decay, input resolution, batch size, or gradient accumulation may be evaluated one variable at a time after the new snapshot baseline.

### Later candidates
Calibration, ensemble, TTA, targeted field-data acquisition, or label adjudication automation require stronger evidence and/or service need.

## Already tested — do not casually repeat

- ResNet LR micro-sweep beyond the confirmed `5e-5` decision;
- 2-epoch head-only staged warm-up;
- CosineAnnealingLR micro-tuning;
- label smoothing around `0.05`;
- additive expected ordinal-distance lambda micro-tuning.

## Promotion rule

A deferred item becomes an experiment only when the plan states:

```text
Observed evidence
Literature / technical basis
Hypothesis
Single controlled change
Frozen data/split
Primary + supporting metrics
Resource metrics if relevant
Acceptance threshold / rejection condition
Stop condition
```

Current stop condition: **no additional ripeness training until a successor data/label snapshot is frozen.**
