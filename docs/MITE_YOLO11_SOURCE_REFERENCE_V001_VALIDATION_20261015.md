# Mite YOLO11 Source-Reference V001 Validation Result — 2026-10-15

Status: **SOURCE_REFERENCE_VALIDATION_FROZEN**

## Run

- Model: YOLO11-Large
- Weights: yolo11l.pt
- Epochs: 100
- Patience: 25
- Input size: 1024
- Seed: 42
- Hardware: NVIDIA GeForce RTX 4060 8GB
- Actual batch: 2 (Ultralytics AutoBatch)
- Source batch reference: 16 on A100 40GB
- Snapshot: MITE-PUBLIC-MORPHOLOGY-V001
- Validation: 203 images / 2,511 instances
- Test: LOCKED

## Validation result

| Metric | Result |
|---|---:|
| Precision | 0.930483 |
| Recall | 0.850092 |
| mAP50 | 0.932762 |
| mAP50-95 | 0.581520 |

### Per-class mAP50-95

| Class | mAP50-95 |
|---|---:|
| Adult_female | 0.612 |
| Immature | 0.447 |
| Viable_egg | 0.686 |

## Source-reference comparison

Official miteVision v210 validation reference:

- Precision ~0.892
- Recall ~0.925
- mAP50 ~0.939
- mAP50-95 ~0.597

Nongtori result:

- mAP50 delta: about -0.006
- mAP50-95 delta: about -0.015

Interpretation:
- the source-reference reproduction is close to the official v210 validation performance;
- Nongtori uses a leakage-safe reassigned split rather than the original Roboflow split;
- Nongtori actual batch is 2 due RTX 4060 VRAM, not source batch 16;
- precision is higher while recall is lower than the official reported aggregate;
- the three life-stage classes remain reference diagnostics, not Nongtori product-facing outputs.

## Checkpoint

Best checkpoint SHA-256:

`eb962a8d879674c9d0fa1cc08ba707ca1f2dc1b094e0e9350baf9e2f2c231529`

## Decision

This validation result satisfies the intended source-reference / portfolio objective.

Next:
1. freeze validation result;
2. perform one-time public test evaluation;
3. do not tune from the public test;
4. stop YOLO morphology research after test freeze;
5. return Nongtori pest ML priority to Thermal-first risk prediction with RGB as auxiliary evidence.
