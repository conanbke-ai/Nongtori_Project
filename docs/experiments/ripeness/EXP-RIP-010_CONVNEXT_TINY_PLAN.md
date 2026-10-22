# EXP-RIP-010 — ConvNeXt-Tiny Backbone Screening

Status: **PLANNED / DEVELOPMENT BENCHMARK ONLY / TEST CLOSED**
Date: **2026-09-15**

## Scope

Use only frozen downloaded `KGCV-RIPENESS-V001`. Drive/field photo-video data are excluded.

- train: 2,243
- valid: 486
- test: 433, closed during screening
- classes in this snapshot: maturity `[0, 1, 4]`

## Evidence

V007 showed that changing backbone representation from ResNet-18 to EfficientNet-B0 improved all aggregate validation metrics after paired multi-seed confirmation.

V009 then showed that changing only the decision head to an ordered ordinal formulation strongly degraded M1 recall and overall metrics. This makes another independent representation family more informative than continued head/loss micro-tuning.

## Hypothesis

ImageNet-pretrained ConvNeXt-Tiny may improve feature representation on the current downloaded benchmark while preserving the same classification objective and data recipe.

## Controlled comparison

Baseline:
- EfficientNet-B0
- weighted CE softmax head
- AdamW
- constant LR `5e-5`
- batch 32
- input 224
- same train augmentation / valid transform

Candidate:
- ConvNeXt-Tiny, ImageNet pretrained
- 3-class linear softmax head
- same weighted CE / optimizer / LR / batch / transforms

## Metrics

Primary:
- validation Macro F1

Supporting:
- Accuracy
- per-class F1, especially M1
- Ordinal MAE
- Weighted Kappa
- confusion matrix
- best epoch
- parameter count
- peak VRAM
- epoch runtime

## Decision rule

- clear regression → REJECT
- positive or near-tied primary metric with better ordinal/M1 behavior → paired 3-seed confirmation
- no architecture-specific tuning before screening decision
- no test evaluation
- no Drive/field data dependency
