# Mite YOLO11 Source-Reference V001

Date: 2026-10-15

## Purpose

This track corrects the source-method alignment gap identified in
`SOURCE_ALIGNMENT_AUDIT_V1`.

It is a source-reference / portfolio experiment, not an automatic production
promotion.

## Source contract

Reference: Gent Lab `miteVision`, TSSM Detection v2, model version 210.

- architecture: YOLO11-Large
- weights: `yolo11l.pt`
- epochs: 100
- patience: 25
- image size: 1024
- source batch: 16
- seed: 42
- pretrained: true
- synthetic data: source v210 reports synthetic-data use

## Nongtori data contract

Snapshot:

`MITE-PUBLIC-MORPHOLOGY-V001`

Classes:

- Adult_female
- Immature
- Viable_egg

Nongtori intentionally does **not** reuse the original Roboflow train/val/test
assignment because the source audit found exact-hash and origin-key leakage.
The frozen leakage-safe split is:

- train: 854
- validation: 203
- test: 192

The test split remains locked during model selection.

## Known execution deviations

The source experiment used an NVIDIA A100 40GB and batch 16.

Nongtori local hardware is materially smaller. The default local run therefore
uses Ultralytics auto-batch and records the actual batch configuration in
`execution-contract.json`.

This is an explicit hardware deviation, not a hidden reproduction claim.

## License boundary

Ultralytics YOLO11 is used here only as a source-reference / portfolio track.
This experiment does not by itself promote Ultralytics YOLO11 into the
Nongtori production/commercial runtime.

The applicable Ultralytics license must be reviewed before any production or
commercial incorporation.

## Commands

Prepare the YOLO directory from the frozen snapshot:

```bash
python -m ml.detector_baseline.mite_yolo11_reference_v001 prepare
```

Install Ultralytics intentionally in the active GPU environment if needed:

```bash
python -m pip install ultralytics
```

Train:

```bash
python -m ml.detector_baseline.mite_yolo11_reference_v001 train \
  --acknowledge-reference-only
```

Do not evaluate the frozen test split until the validation-selected checkpoint
and result are reviewed and frozen.
