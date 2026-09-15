# Nongtori Ripeness Tuning Backlog

Status: **CANONICAL BACKLOG / DO NOT BLIND-SWEEP**
Updated: **2026-09-15**

## Purpose

This backlog separates **things worth investigating** from **things already tested and rejected**. It exists to prevent repeated parameter tweaking and to keep the improvement path evidence-driven.

A backlog item is not permission to run a grid search. Before execution it must have:

1. observed project evidence;
2. literature/technical basis where applicable;
3. one clear hypothesis;
4. controlled variables;
5. acceptance/rejection criteria.

## Current evidence

V007 paired 3-seed confirmation (`20260911/12/13`) produced:

| Metric | ResNet-18 mean ± std | EfficientNet-B0 mean ± std | EfficientNet Δ |
|---|---:|---:|---:|
| Macro F1 | 0.9614 ± 0.0045 | **0.9686 ± 0.0064** | **+0.0072** |
| Accuracy | 0.9643 ± 0.0043 | **0.9698 ± 0.0063** | **+0.0055** |
| Ordinal MAE ↓ | 0.0418 ± 0.0063 | **0.0322 ± 0.0097** | **-0.0096** |
| Weighted Kappa | 0.9734 ± 0.0045 | **0.9771 ± 0.0070** | **+0.0037** |

EfficientNet-B0 won Macro F1 on 2/3 paired seeds and improved every aggregate primary/ordinal metric. It is therefore the preferred architecture candidate, subject to final resource/test/field gates.

## Priority A — do before further hyperparameter tuning

### A1. Validation hard-example / error-ceiling audit

**Question:** Are the remaining errors caused mainly by model capacity, label ambiguity, crop quality, or domain variation?

Required outputs:
- prediction export for selected ResNet and EfficientNet checkpoints;
- error intersection and model-specific error sets;
- true/predicted class, confidence, source asset, bbox, source/farm context;
- confusion transition counts;
- repeated hard-sample ranking;
- review buckets: `LABEL_AMBIGUITY`, `CROP_QUALITY`, `DOMAIN_VARIATION`, `MODEL_DISAGREEMENT`, `LIKELY_MODEL_LIMIT`, `REVIEW_REQUIRED`.

**Why first:** a validation set of 486 samples is already in the high-accuracy regime, so a few samples materially change headline metrics. The next improvement mechanism should be selected from residual-error evidence rather than from a target such as `0.98`.

### A2. EfficientNet resource acceptance

Record and compare:
- parameter count;
- peak VRAM;
- epoch runtime;
- inference latency/FPS where service inference matters;
- checkpoint size.

Do not promote an architecture solely on validation score if the operational cost is disproportionate.

### A3. Independent test/field gate

After architecture and tuning decisions are frozen, evaluate the selected candidate on the untouched test/field holdout according to `MODEL_ACCEPTANCE_POLICY.md`. Do not repeatedly tune against this result.

## Priority B — conditional tuning, only after A1

### B1. Targeted augmentation

Run only if the error audit shows concentration in specific acquisition conditions such as illumination, occlusion, framing, scale, or viewpoint.

Candidate dimensions to design deliberately:
- brightness/contrast/exposure;
- crop/scale;
- occlusion;
- viewpoint robustness.

Do **not** blindly increase augmentation strength.

### B2. Class/boundary treatment

Run only if errors remain concentrated at a specific maturity boundary and label audit confirms the labels are reliable.

Possible research directions:
- genuinely ordinal heads/objectives rather than a small additive penalty;
- boundary-aware or cost-sensitive classification;
- calibrated uncertainty / abstention for ambiguous samples.

V005 label smoothing and V006 additive expected-distance regularization are already rejected; do not repeat nearby coefficients without a new structural hypothesis.

### B3. Architecture follow-up

ConvNeXt-Tiny remains a literature-grounded architecture candidate, but should be tested only if:
- EfficientNet resource/field acceptance is insufficient; or
- A1 shows residual representation errors that justify another backbone.

Do not run architecture tournaments simply to chase a higher validation number.

### B4. EfficientNet-specific optimization

Only after EfficientNet-B0 is confirmed as the architecture to retain and A1 provides a reason to tune it.

Potential dimensions:
- architecture-appropriate LR confirmation;
- discriminative LR / layer-wise decay;
- input resolution;
- batch size/gradient accumulation if resource-bound.

Each must be isolated. No combined tuning bundle.

## Priority C — later / only with stronger evidence

- calibration (ECE/Brier/temperature scaling) if confidence is consumed by decision policy;
- lightweight ensemble only if complementary model-error sets justify the added inference cost;
- TTA only if deployment latency permits and error audit shows augmentation-consistent gains;
- additional field-data acquisition targeted at known failure conditions;
- label adjudication protocol if human ambiguity is a measurable ceiling.

## Already tested — do not casually repeat

- full fine-tuning LR micro-sweep around the ResNet recipe;
- 2-epoch head-only staged warm-up;
- CosineAnnealingLR parameter micro-tuning;
- label smoothing around `0.05`;
- additive expected ordinal-distance lambda micro-tuning.

## Promotion rule

A tuning item moves from backlog to experiment only when the experiment plan states:

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

The goal is not `Macro F1 >= 0.98` by itself. The goal is to reduce **explainable, operationally meaningful residual error** without leakage, cherry-picking, or unjustified complexity.
