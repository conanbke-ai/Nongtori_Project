# Nongtori Ripeness Tuning Backlog

Status: **CANONICAL BACKLOG / DO NOT BLIND-SWEEP**
Updated: **2026-09-15 — after V008 residual-error audit**

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

Conclusion: the current residual problem is highly localized at the **M0/M1 boundary**, not a broad maturity-classification failure. Eight shared errors require source/crop/label review before additional model tuning.

## Priority A — current work

### A1. M0/M1 boundary hard-example review — NEXT

Review all 12 EfficientNet errors plus model-disagreement samples against original crop/source context.

Assign review taxonomy:
- `LABEL_AMBIGUITY`
- `CROP_QUALITY`
- `DOMAIN_VARIATION`
- `LIKELY_MODEL_LIMIT`
- `MODEL_DISAGREEMENT`
- `REVIEW_REQUIRED`

Required analysis:
- inspect original crop and, when available, source image context;
- true/predicted maturity and confidence;
- M0→M1 vs M1→M0 direction;
- shared vs architecture-specific error;
- lighting/exposure/viewpoint/occlusion/crop framing indicators;
- repeated source/farm/session concentration;
- whether the human label is visually defensible.

**Stop condition:** do not launch another training experiment until the dominant residual-error category is identified.

### A2. EfficientNet resource acceptance

Record and compare parameter count, peak VRAM, epoch runtime, checkpoint size, and inference latency/FPS where service inference matters.

### A3. Independent test/field gate — after tuning freeze

Evaluate the selected frozen candidate once according to `MODEL_ACCEPTANCE_POLICY.md`. Do not repeatedly tune against test/field results.

## Priority B — conditional tuning selected by A1 evidence

### B1. Targeted augmentation
Run only if residual errors cluster by illumination, exposure, occlusion, framing, scale, or viewpoint. Tune the observed acquisition failure, not generic augmentation strength.

### B2. M0/M1 boundary formulation
Run only if labels/crops are clean and the boundary remains model-limited. Research candidates may include a genuinely ordinal head/objective, boundary-aware/cost-sensitive classification, or calibrated abstention for ambiguous samples.

V005 label smoothing and V006 additive expected-distance regularization are already rejected and must not be repeated as coefficient micro-sweeps.

### B3. Architecture follow-up
ConvNeXt-Tiny remains a literature-grounded candidate only if residual representation evidence or EfficientNet operational cost justifies it. Do not run an architecture tournament merely to chase `0.98`.

### B4. EfficientNet-specific optimization
Only after A1 identifies a model-side bottleneck. Potential isolated dimensions: architecture-appropriate LR confirmation, discriminative LR/layer-wise decay, input resolution, or batch/gradient accumulation if resource-bound.

## Priority C — later / stronger evidence required

- calibration (ECE/Brier/temperature scaling) if confidence is consumed by decision policy;
- lightweight ensemble only if clean-label complementary errors justify inference cost;
- TTA only if latency permits and error evidence supports it;
- targeted field-data acquisition for observed failure conditions;
- label adjudication protocol if human ambiguity is a measurable ceiling.

## Already tested — do not casually repeat

- ResNet LR micro-sweep beyond the confirmed `5e-5` decision;
- 2-epoch head-only staged warm-up;
- CosineAnnealingLR micro-tuning;
- label smoothing around `0.05`;
- additive expected ordinal-distance lambda micro-tuning.

## Promotion rule

A backlog item becomes an experiment only when the plan states:

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

The goal is not `Macro F1 >= 0.98` by itself. On 486 validation samples, EfficientNet currently makes 12 errors and `>=0.98` accuracy would require at most 9; only three corrected samples separate those headline values. The goal is therefore to reduce **explainable, operationally meaningful residual error** without leakage, cherry-picking, or unjustified complexity.
