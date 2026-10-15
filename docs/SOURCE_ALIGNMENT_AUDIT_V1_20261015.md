# Nongtori Source Alignment Audit V1 — 2026-10-15

Status: **CANONICAL AUDIT / CORRECTIVE ACTION REQUIRED**

## 1. Audit rule

A Nongtori model is not considered source-aligned merely because it uses a cited public dataset.

For every model family the required chain is:

```text
source paper
→ official implementation
→ source target definition
→ source preprocessing
→ source architecture
→ source training recipe
→ source evaluation protocol
→ Nongtori deviations
→ deviation rationale
→ reproduction / replacement decision
```

Dataset provenance and model-method provenance are separate gates.

---

## 2. Pest / TSSM detector

### Source evidence

Primary source:
- Gent Lab / miteVision
- dataset: TSSM Detection v2
- official code: `mswiseman/miteVision`
- pinned Nongtori morphology source: Roboflow version 210

Official v210 training family:
- model: Ultralytics YOLO11-Large
- input size: 1024
- epochs: 100
- patience: 25
- batch: 16
- pretrained: true
- optimizer: Ultralytics auto
- seed: 42
- synthetic data used
- v210 classes: Adult_female / Immature / Viable_egg

Official reported v210:
- validation mAP50: 0.939
- validation mAP50-95: 0.597
- test mAP50: 0.883
- test mAP50-95: 0.601

### Current Nongtori implementation

Executed:
- Faster R-CNN MobileNetV3-FPN field-context V001
- Faster R-CNN morphology-transfer V002

V001 frozen public field-context test:
- mite mAP50: 0.844664
- mite mAP50-95: 0.694272

### Alignment judgment

`NOT_SOURCE_ALIGNED / VALID_ENGINEERING_BASELINE`

The Faster R-CNN work is valid experimental evidence but it is not a reproduction of the cited TSSM source method.

The original requirement to design from source material was not satisfied at the architecture/training-recipe level.

### Corrective action

1. Preserve Faster R-CNN V001/V002 as historical baseline evidence.
2. Do not promote V002 automatically to canonical production architecture.
3. Add a YOLO11 source-reference track using the frozen Nongtori snapshots.
4. Record explicit licensing scope for Ultralytics use.
5. Compare source-reference validation against Faster R-CNN only after the YOLO configuration is frozen.
6. Stop broad architecture search after this correction; product integration and field validation remain priority.

---

## 3. Ripeness / phenological stage

### Source evidence

Primary source:
- Yang et al. 2024, KGCV Strawberry
- official repository: `DigitalAgUMN/KGCV_Strawberry`
- official dataset/model archive: Zenodo 10957909

The official implementation contains two distinct vision tasks.

#### Main stage detection

`KGCV_Strawberry_Train_FasterRCNN.py`

- architecture: Faster R-CNN ResNet50-FPN
- COCO pretrained
- target: strawberry bounding box + main phenological stage
- classes: seven phenological stages plus background
- epochs: 50
- optimizer: SGD
- LR: 0.005
- momentum: 0.8
- weight decay: 0.0005
- scheduler: StepLR gamma 0.95
- train augmentation includes horizontal flip and photometric distortion

#### Trait + decimal phenological stage estimation

`KGCV_Strawberry_Train_CNN.py`

- architecture: DenseNet121
- outputs: diameter + length + decimal phenological stage
- crop size: 256
- epochs: 100
- optimizer: Adam
- classifier/head LR: 0.005
- base-network LR coefficient: 0.01
- LR decay: 0.98 per epoch
- batch size: 32
- train augmentation: H/V flip, rotation, brightness/saturation jitter

### Current Nongtori implementation

`KGCV-RIPENESS-V001` maps:
- small g / green → M0
- white → M1
- red / overripe → M4
- turning red → excluded

Current benchmark architecture line:
- ResNet18 baseline
- EfficientNet-B0 preferred benchmark candidate
- discrete 0/1/4 classification
- weighted cross-entropy
- AdamW
- 224 crop
- validation Macro F1 selection

### Alignment judgment

`PARTIALLY_SOURCE_GROUNDED / NOT_SOURCE_METHOD_ALIGNED`

Strengths retained:
- exact source provenance
- immutable snapshot
- leakage-safe split
- original labels preserved before Nongtori mapping
- controlled validation-only experiments

Material deviations:
- source decimal phenological-stage supervision is not used
- source DenseNet121 multitarget regression is not reproduced
- source Faster R-CNN stage detector is not reproduced
- source seven-stage target is collapsed to 0/1/4
- architecture and training recipe were selected from generic literature screening rather than first reproducing the source method

### Corrective action

1. Keep EfficientNet-B0 results as `DEVELOPMENT_BENCHMARK_ONLY`.
2. Do not call EfficientNet-B0 the source-derived canonical ripeness architecture.
3. Before further generic ripeness tuning, implement a source-aligned successor:
   - DenseNet121 decimal-stage regression reproduction on usable KGCV targets, and/or
   - source Faster R-CNN main-stage reproduction if the product task needs joint detection+stage.
4. Explicitly compare source target semantics with the Nongtori field 0–4 policy before selecting the final task formulation.
5. Re-open architecture optimization only after source-aligned reproduction and field-label freeze.

---

## 4. Grade / quality

### Current Nongtori implementation

Current selective auto-grade code uses fixed weight thresholds:

```text
<12g       → JM_WEIGHT_CANDIDATE
12–16g     → MD_WEIGHT
16–22g     → HI_WEIGHT
>=22g      → SP_WEIGHT
```

These bands are used in weight-model grade accuracy, threshold-crossing audits and selective auto-grade policy.

### External standard check

The Korean agricultural standard for fresh domestic strawberries separates:

1. **quality grade**: 특 / 상 / 보통, using size uniformity plus color, freshness and defects;
2. **size class**:
   - S: <12g
   - M: 12–17g
   - L: 17–25g
   - 2L: >=25g

Therefore the current `12/16/22` bands do not match the checked national size-class boundaries and do not represent the full official quality grade.

### Alignment judgment

`FIELD_POLICY_SOURCE_CONFIRMED / TERMINOLOGY_SEPARATION_REQUIRED`

The existing 12/16/22 thresholds are user-confirmed as the real operational classification rule used by the Hadong strawberry Nonghyup direct-sales context. They therefore remain a valid **field/business grade policy** for Nongtori. They are not the same thing as the national official size class or official quality grade.

### Corrective action

1. Preserve existing V001 weight benchmark artifacts unchanged as historical evidence.
2. New code/docs must distinguish:
   - `OFFICIAL_SIZE_CLASS`
   - `OFFICIAL_QUALITY_GRADE`
   - `NONGTORI_INTERNAL_WEIGHT_BAND`
   - farm/customer-specific commercial grading rules
3. Preserve `12/16/22` as the Hadong field/business grading rule and name it explicitly as such.
4. Do not present `12/16/22` as the national official strawberry size or quality standard.
5. Register both the Hadong field/business policy and the national standard as separate policy sources.
6. Final product grade logic must keep field-business grade, official size class, and official quality grade distinct.

---

## 5. Canonical decisions after audit

| Domain | Existing work | Source alignment | Canonical status |
|---|---|---|---|
| TSSM | Faster R-CNN V001/V002 | Low | historical baseline / correction required |
| Ripeness | ResNet18 → EfficientNet-B0 | Partial | development benchmark only |
| Grade | 12/16/22 weight bands | field/business source confirmed | Hadong field-business grade policy |
| Data governance | snapshots / hashes / leakage controls | Strong | retain |
| Test-lock policy | validation selection + frozen test | Strong | retain |

## 6. Immediate order

1. Finish currently running Faster R-CNN V002 only as historical evidence; do not extend the Faster R-CNN research line.
2. Build one source-reference YOLO11 TSSM track.
3. Add KGCV source-aligned ripeness reproduction before any new generic architecture tuning.
4. Correct grade terminology/provenance before product/UI claims.
5. Then return effort to inference integration, field acceptance and portfolio completion.

