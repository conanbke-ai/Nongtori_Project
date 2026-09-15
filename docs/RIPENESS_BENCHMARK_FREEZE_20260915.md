# Nongtori Ripeness Development Benchmark Freeze — 2026-09-15

Status: **FROZEN DEVELOPMENT BENCHMARK / NOT FINAL FIELD MODEL**

## Purpose

This document freezes the meaning of the current `KGCV-RIPENESS-V001` experiment line so that its metrics are not misrepresented as final Nongtori field performance.

## What is frozen

The following work is preserved as **development-benchmark evidence**:

- external/public-source normalization and frozen snapshot construction;
- leakage-safe split and shared immutable crop cache;
- ResNet-18 baseline reproduction;
- learning-rate confirmation;
- staged fine-tuning rejection;
- cosine scheduler rejection;
- label-smoothing rejection;
- additive ordinal-distance loss rejection;
- EfficientNet-B0 architecture screening and paired multi-seed confirmation;
- V008 residual-error audit.

## Current benchmark conclusion

For `KGCV-RIPENESS-V001` only:

- EfficientNet-B0 is the preferred validation architecture candidate;
- paired multi-seed confirmation improved aggregate Macro F1 / Accuracy / Ordinal MAE / Weighted Kappa over ResNet-18;
- V008 showed that all 12 EfficientNet residual validation errors were confined to the M0/M1 boundary;
- 8 of those 12 were the same errors made by ResNet-18;
- M4 was perfect on the audited validation checkpoint.

These facts support engineering decisions for the current benchmark. They do **not** establish the final maturity taxonomy, final field accuracy, production acceptance, or actual farm-domain generalization.

## Why further generic tuning is frozen

The user's field/photo/video dataset is still being organized and a material portion of the current material is development/testing data. Therefore:

1. the eventual data distribution can change;
2. the final field-label definition can change;
3. the current `0/1/4` benchmark classes are not sufficient evidence for a finalized 0–4 field annotation guideline;
4. chasing a headline validation threshold such as `0.98` on the current 486-sample validation set risks optimizing a temporary benchmark instead of the final task.

Accordingly, generic LR/scheduler/loss/backbone micro-tuning is paused after V008 unless a new experiment is directly justified by data/label evidence.

## Current model status

```text
Snapshot      : KGCV-RIPENESS-V001
Role          : development benchmark
Preferred net : EfficientNet-B0
Selection     : validation Macro F1
Test tuning   : prohibited
Field status  : NOT FIELD VALIDATED
Production    : NOT APPROVED
```

## Resume condition

Create a new snapshot (for example `KGCV-RIPENESS-V002` or a field-inclusive successor) and re-open model optimization only after enough of the following are available:

- field/photo/video organization reaches a stable revision;
- maturity label policy is reviewed and versioned;
- flower / fruit-set / non-fruit treatment is explicit;
- 0–4 stage criteria and ambiguous-boundary rules are explicit;
- label-review/adjudication process is defined;
- new normalized manifest and leakage-safe split are frozen.

Then re-run a clean baseline before carrying forward any previous tuning assumption.

## Portfolio interpretation

The value of V001–V008 is not a claim of final production accuracy. It demonstrates a complete ML engineering workflow:

`source governance → normalization → immutable snapshot → leakage control → observable GPU training → controlled experiments → multi-seed confirmation → residual-error audit → evidence-based stop condition`.
