# EXP-RIP-009 — EfficientNet-B0 Rank-Consistent Ordinal Head

Status: **PLANNED / DEVELOPMENT BENCHMARK ONLY / TEST CLOSED**
Date: **2026-09-15**

## Scope clarification

This experiment deliberately excludes current Google Drive / field-photo / field-video data because that inventory is still being organized.

V009 uses only the already materialized and frozen external development snapshot:

- snapshot: `KGCV-RIPENESS-V001`
- physical source images: 1,477
- eligible object crops: 3,162
- classes used by this snapshot: maturity values `[0, 1, 4]`
- frozen split: train 2,243 / valid 486 / test 433
- test set: **closed during V009 screening**

The result must be described as development-benchmark evidence only. It must not be reported as field performance or a finalized 0–4 field-label model.

## Observed evidence

V007 confirmed EfficientNet-B0 as the stronger development-benchmark backbone over ResNet-18 on paired multi-seed validation.

V008 then localized the selected EfficientNet checkpoint's 12 validation errors to the adjacent M0/M1 boundary:

- M0 → M1: 10
- M1 → M0: 2
- M4 errors: 0

V005 label smoothing and V006 an additive expected-distance penalty were already rejected. Therefore V009 does **not** retry a nearby scalar regularization coefficient.

## Literature / technical basis

Ordinal labels carry ordering information that ordinary multi-class cross-entropy does not explicitly encode. Rank-consistent ordinal-regression work such as CORAL (Cao, Mirjalili, Raschka, Pattern Recognition Letters, 2020, DOI `10.1016/j.patrec.2020.11.008`) converts an ordered K-class problem into K-1 cumulative threshold tasks and constrains the output formulation so the rank probabilities are consistent.

Nongtori V009 uses the same core idea but implements it locally as a monotonic cumulative-threshold head rather than adding a third-party training dependency.

## Hypothesis

For the current downloaded benchmark only, replacing the 3-way softmax head with a structurally ordinal cumulative-threshold head may reduce adjacent-stage confusion, especially M0/M1, while preserving or improving Macro F1 and ordinal metrics.

## Controlled comparison

Paired screening under one seed:

### Baseline

- backbone: ImageNet-pretrained EfficientNet-B0
- head: 3-class linear softmax
- objective: weighted CrossEntropy
- optimizer: AdamW
- LR: constant `5e-5`
- augmentation/input/batch: V007 recipe

### Candidate

- backbone: same ImageNet-pretrained EfficientNet-B0
- head: one shared latent maturity score + two ordered thresholds
- target ranks: maturity `[0,1,4]` → ordinal ranks `[0,1,2]`
- cumulative targets:
  - rank 0 → `[0,0]`
  - rank 1 → `[1,0]`
  - rank 2 → `[1,1]`
- objective: BCE-with-logits over the two cumulative thresholds
- threshold positive weights are derived from the frozen training split; no tuned coefficient is introduced
- optimizer/LR/augmentation/input/batch: same as baseline

The head guarantees ordered thresholds by parameterizing the second cutpoint as `cut1 + softplus(gap)`.

## Metrics

Primary:
- validation Macro F1

Supporting:
- Accuracy
- per-class F1, especially M1
- Ordinal MAE
- Weighted Kappa
- confusion matrix
- M0→M1 / M1→M0 transition counts
- best epoch
- peak VRAM
- epoch runtime
- parameter count

## Acceptance / rejection

### Positive screening

Promote to paired 3-seed confirmation only if:

- Macro F1 improves without a material regression in ordinal MAE/Kappa; **or**
- Macro F1 is effectively tied but M1 F1 and M0/M1 confusion improve materially with no broad-class regression.

### Reject

Reject V009 if:

- Macro F1 clearly decreases;
- ordinal MAE/Kappa worsens without a compensating primary-metric benefit;
- errors shift from M0/M1 into previously stable M4;
- the structural complexity adds no meaningful validation benefit.

## Stop condition

- screening first;
- no test evaluation;
- no threshold/loss coefficient sweep;
- no Drive/field data dependency;
- no production/field claim;
- if positive, run paired multi-seed confirmation before retaining the formulation.
