# Mite Field Detector V001 Test Freeze — 2026-10-14

## Frozen checkpoint

- Model: `fasterrcnn_mobilenet_v3_large_fpn`
- Snapshot: `MITE-PUBLIC-FIELD-CONTEXT-V001`
- Checkpoint epoch: 12
- Selection: validation only
- Public test: evaluated once after checkpoint freeze

## Official public test result

- Images: 424
- GT boxes: 1,423
- Mite mAP50: 0.844664
- Mite mAP50-95: 0.694272
- Mite Precision@0.5: 0.766216
- Mite Recall@0.5: 0.803116
- Macro mAP50: 0.865834
- Macro mAP50-95: 0.708821

### Per-class mAP50-95

- Tetranychus Urticae: 0.694272
- dry: 0.495859
- gray_mold: 0.792435
- scorch: 0.852720

## Interpretation

The public strawberry-context baseline generalizes consistently across its frozen source test split. The test result is report-only and cannot be used for V001 model, threshold, hyperparameter, or checkpoint selection.

This result does not establish Nongtori field readiness. Actual Nongtori field data remains the independent acceptance/calibration source.

## Next experiment

A successor experiment may use `MITE-PUBLIC-MORPHOLOGY-V001` as a morphology pretraining/transfer source and compare against this frozen V001 baseline. The V001 public test must remain untouched during successor model selection.
