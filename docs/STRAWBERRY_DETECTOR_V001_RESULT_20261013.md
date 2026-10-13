# Strawberry Detector V001 Result Freeze — 2026-10-13

## Scope

This document freezes the first Nongtori strawberry object-detection baseline.

- Model: `fasterrcnn_mobilenet_v3_large_fpn`
- Foreground class: `strawberry`
- Source: DATA-RIP-001 / Strawberry-DS
- Images: 247
- Bounding boxes: 1,083
- Frozen split: train 172 / validation 49 / test 26
- Test GT boxes: 104

## Selection policy

The best checkpoint was selected using validation only.

- Best epoch: 12
- Validation mAP50: 0.8318
- Validation mAP50-95: 0.5296
- Validation Precision@0.5: 0.8630
- Validation Recall@0.5: 0.8400

The official test split was locked until checkpoint selection was complete.

## Frozen test result

- mAP50: 0.713840
- mAP50-95: 0.435940
- Precision@0.5: 0.817204
- Recall@0.5: 0.730769

Per-IoU AP:

| IoU | AP |
|---|---:|
| 0.50 | 0.713840 |
| 0.55 | 0.695408 |
| 0.60 | 0.695080 |
| 0.65 | 0.665476 |
| 0.70 | 0.550964 |
| 0.75 | 0.447667 |
| 0.80 | 0.342014 |
| 0.85 | 0.190066 |
| 0.90 | 0.058890 |
| 0.95 | 0.000000 |

## Interpretation

The detector is a useful public-data baseline but is not field-ready.

The validation-to-test drop is preserved as generalization evidence. The frozen test result must not be used to choose a new model, hyperparameter, score threshold, data augmentation policy, or training duration for V001.

Successor work should be driven by independent field/external data or a new immutable training snapshot.
