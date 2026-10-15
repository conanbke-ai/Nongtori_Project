# Mite Morphology Transfer V002 Result Freeze — 2026-10-15

Status: **REJECTED AS IMPROVEMENT / HISTORICAL EVIDENCE ONLY**

## Experiment

Stage 1:
- Faster R-CNN MobileNetV3-FPN morphology pretraining
- snapshot: MITE-PUBLIC-MORPHOLOGY-V001
- classes: Adult_female / Immature / Viable_egg
- max epochs: 15
- patience: 5
- test: locked

Stage 2:
- transfer all detector representation except class-specific box predictor
- fine-tune on MITE-PUBLIC-FIELD-CONTEXT-V001
- checkpoint selection: field validation mite mAP50-95
- test: locked

## Morphology result

Best morphology epoch: 14

- macro AP50: 0.2410
- macro mAP50-95: 0.0939

The stage did not early-stop. It reached the hard 15-epoch ceiling with stale=1/5, so it is not evidence of a fully converged morphology representation.

## Field result

Best field epoch: 10

- mite mAP50: 0.8498
- mite mAP50-95: 0.6831
- Precision@0.5: 0.8112
- Recall@0.5: 0.7808
- macro mAP50-95: 0.7154

Frozen V001 validation reference:

- mite mAP50-95: 0.6840

Delta:

- V002 - V001 mite mAP50-95 = -0.0009

## Decision

V002 does not beat V001 on the predeclared primary validation metric.

Therefore:
- do not evaluate the V002 test split;
- do not promote V002;
- do not rescue-tune this Faster R-CNN transfer formulation;
- preserve the run as negative/historical evidence;
- move to the source-aligned YOLO11-Large reference track.

This decision also follows SOURCE_ALIGNMENT_AUDIT_V1, which classifies the Faster R-CNN TSSM line as valid engineering evidence but not source-method aligned to miteVision.
