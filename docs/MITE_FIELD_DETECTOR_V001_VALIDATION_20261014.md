# Mite Field Detector V001 Validation Freeze — 2026-10-14

## Scope

- Model: `fasterrcnn_mobilenet_v3_large_fpn`
- Snapshot: `MITE-PUBLIC-FIELD-CONTEXT-V001`
- Classes:
  - Tetranychus Urticae
  - dry
  - gray_mold
  - scorch
- Selection split: validation
- Test split: locked during training

## Frozen validation result

Best epoch: 12

- mite mAP50: 0.8536
- mite mAP50-95: 0.6840
- mite Precision@0.5: 0.8021
- mite Recall@0.5: 0.7973
- macro mAP50-95: 0.7057

Training stopped at epoch 17 after five consecutive validation non-improvements.

## Selection policy

The epoch-12 checkpoint is frozen before public test evaluation.

The official public test split may now be evaluated once for reporting only. Test results must not be used to:
- change the model architecture
- change hyperparameters
- tune the score threshold
- change training duration
- choose a replacement V001 checkpoint

## Acceptance boundary

This is a public strawberry-context development baseline.

Field readiness remains `NOT_ESTABLISHED`. Actual Nongtori field data remains the independent acceptance/calibration source.
