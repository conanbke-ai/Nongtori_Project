# Weight Estimation Product Role V1

Status: **PORTFOLIO_V1 / HARDWARE_AGNOSTIC**

## 1. Why Nongtori keeps vision-based weight estimation

Nongtori does not assume that every harvesting robot lacks a weighing sensor.

The current portfolio cannot guarantee the hardware specification of a future harvesting device, so weight estimation is implemented as a hardware-independent capability that can operate from RGB observations alone.

The purpose is therefore:

- validate whether fruit weight can be estimated from visual evidence;
- support pre-harvest weight / grade estimation before physical weighing is possible;
- provide a fallback when the connected device does not expose a reliable weight sensor;
- keep the grading pipeline independent from one robot or sorter vendor;
- document the limits of vision-only estimation instead of claiming that AI replaces a scale.

If a future device provides a trusted measured weight, Nongtori must use that measured value before a vision estimate.

## 2. Runtime weight source contract

Implementation status: **RUNTIME_V1_IMPLEMENTED**

- append-only `fruit_weight_observations` persistence implemented;
- resolved source priority implemented;
- public API allows manual measured weight only;
- sensor and vision writes are internal service operations;
- actual harvesting-device/load-cell adapter is **not yet connected**.

Canonical runtime source order:

```text
SENSOR_MEASURED
→ MANUAL_MEASURED
→ VISION_ESTIMATED
```

Semantics:

| Source | Meaning | Default trust |
|---|---|---|
| `SENSOR_MEASURED` | load cell / scale / harvesting equipment measured value | highest |
| `MANUAL_MEASURED` | operator-entered measured value | measured, but provenance must be retained |
| `VISION_ESTIMATED` | model estimate from RGB/RGB-D or derived geometry | fallback / pre-harvest |

The source value must travel with the weight itself.

Recommended domain fields:

```text
weight_g
weight_source
weight_model_name       # VISION_ESTIMATED only
weight_model_version    # VISION_ESTIMATED only
weight_confidence       # optional; calibrated estimate only
measured_at             # measured source when available
```

A measured value must not be silently replaced by a model estimate.

## 3. Weight grade is not the final commercial grade

Nongtori keeps the current fixed weight boundaries:

```text
>= 22 g  → SP_WEIGHT
>= 16 g  → HI_WEIGHT
>= 12 g  → MD_WEIGHT
<  12 g  → JM_WEIGHT_CANDIDATE
```

These are **weight-grade boundaries**, not a complete reinterpretation of the field `Grade` label.

In particular:

```text
JM_WEIGHT_CANDIDATE != field Grade=JM
```

Field `JM` can also represent deformity, over-ripeness, or other marketability issues. The final product flow remains:

```text
weight input
→ Weight Grade
→ Quality Override
→ Final Grade
```

Shape, appearance, health, over-ripeness, and other quality evidence may override a weight-only provisional grade.

The 12 / 16 / 22 g thresholds are frozen product rules for the current experiment line. Validation/test results must not be used to move them.

## 4. Why 1–2 g error is operationally important

Weight MAE alone is insufficient for Nongtori.

For example:

```text
21.8 g → 22.3 g
absolute error = 0.5 g
but grade crosses HI_WEIGHT → SP_WEIGHT
```

while:

```text
25.0 g → 23.0 g
absolute error = 2.0 g
but both remain SP_WEIGHT
```

Therefore a smaller numerical error can create a larger operational error.

Required evaluation must include both regression and boundary metrics.

### Regression metrics

- MAE g
- RMSE g
- R²
- bias g
- max absolute error g

### Operational grade metrics

- weight-grade accuracy
- grade confusion matrix
- 12 g threshold crossing count/rate
- 16 g threshold crossing count/rate
- 22 g threshold crossing count/rate
- boundary distance bands: <=0.5 g / <=1 g / <=2 g / <=3 g / >3 g
- severe grade error count
- paired residual comparison between geometry, RGB, and future fusion models

A model with lower global MAE is not automatically preferred if it creates more threshold crossings.

## 5. Model roadmap

Current portfolio experiment order:

```text
Geometry V001
→ threshold residual audit
→ RGB V001
→ paired Geometry vs RGB residual comparison
→ RGB + Geometry fusion
→ optional weight + ordinal-grade multi-task experiment
→ uncertainty / re-measure zone evaluation
```

The multi-task stage is optional and must not be introduced before the independent baselines are frozen.

If used, ordinal grade learning should preserve the ordered thresholds instead of treating SP/HI/MD/JM as unrelated classes.

## 6. Uncertainty and re-measure policy

A production-like system should not pretend that every visual estimate is equally safe.

For estimates close to a grade boundary, a future policy may emit:

```text
estimated_weight_g
provisional_weight_grade
boundary_risk
recommended_action = RE_MEASURE | ACCEPT_ESTIMATE
```

The size of a re-measure band must be calibrated on validation data and frozen before test evaluation. It must not be chosen from the test set.

If a trusted physical measurement becomes available, it replaces the visual estimate for final weight-grade calculation.

## 7. Portfolio claim

The portfolio claim is:

> Nongtori implements a vendor-independent vision weight-estimation module because the target harvesting hardware is not fixed. The module is evaluated not only by regression error but also by the operational effect of 12/16/22 g grade-boundary crossings. A trusted measured weight, when available, has priority over AI estimation.

The portfolio must **not** claim:

- that all harvesting robots lack scales;
- that vision is more accurate than a load cell;
- that the current RGB baseline is production-approved;
- that a 1–2 g MAE is automatically acceptable for grading;
- that `JM_WEIGHT_CANDIDATE` is identical to field `Grade=JM`.

## 8. Current evidence

Current frozen geometry baseline on `WEIGHT-DRYAD-V001`:

- primary: `LINEAR_WIDTH_HEIGHT_AREA`
- test MAE: 1.4125 g
- test RMSE: 2.1850 g
- test R²: 0.9003
- test weight-grade accuracy: 0.8205

Interpretation:

- geometry contains strong weight information;
- the error is still operationally meaningful near grade thresholds;
- the result is a baseline, not a final grading model;
- RGB V001 is being evaluated on the same immutable `FRUIT_ID` split.

## 9. Dataset role clarification

`WEIGHT-DRYAD-V001` strict RGB-weight cohort는 524 FRUIT_ID이며, official split은 train 367 / validation 79 / test 78이다.

Validation 79는 전체 확보 데이터가 79개라는 뜻이 아니다. 독립 평가 단위가 FRUIT_ID이므로 같은 fruit의 22 RGB views는 하나의 독립 fruit sample로 취급한다.

후속 개발에서 official validation을 반복적으로 소비하지 않기 위해 train 367 fruit 내부 deterministic 5-fold CV를 개발 단계의 첫 선택 표면으로 사용한다. Official validation은 방법 고정 후 확인용, official test는 locked holdout으로 유지한다.

## 10. Existing-data reuse gate

Before introducing a new model family, Nongtori audits whether already-acquired Dryad records can expand train-only supervision.

Current source facts:

- 1,571 valid with-calyx weight targets exist in Dryad metadata.
- the strict RGB-weight cohort contains 524 FRUIT_ID with approved exact-22-view RGB assets.
- fruit outside the strict RGB cohort must not be called RGB training data merely because weight metadata exists.

`geometry_auxiliary_audit_v1` identifies fruit with valid `weight_with_calyx_g + width_mm + height_mm` outside the strict 524 cohort. These are candidates for Geometry V2 train-only augmentation while official validation 79 and test 78 remain unchanged.

This does not enlarge the official validation/test sample, and it does not convert missing RGB assets into synthetic image evidence.

Command:

```bash
python -m ml.weight_baseline.geometry_auxiliary_audit_v1
```

## 11. Geometry V2 auxiliary experiment

The auxiliary audit identified 1,047 fruit outside the strict RGB cohort with valid weight, width and height. This makes a Geometry V2 train-only augmentation experiment materially worthwhile.

Compared regimes:

```text
STRICT_ONLY
= official train 367

STRICT_PLUS_AUXILIARY
= official train 367 + auxiliary 1,047
= 1,414 geometry training fruit
```

Regime selection is performed only on 5-fold OOF predictions from the official train cohort. Auxiliary fruit may enter fitting but never become official validation/test observations.

Official validation 79 is used only after regime selection for confirmation. Official test 78 remains locked for this development step.

Command:

```bash
python -m ml.weight_baseline.geometry_v002
```

## 12. Geometry auxiliary result interpretation

Naively adding all 1,047 auxiliary geometry-weight fruit was tested and rejected on official-train 5-fold OOF.

```text
STRICT_ONLY
MAE 1.3698g
grade errors 59
threshold crossings 60

STRICT_PLUS_AUXILIARY
MAE 1.3932g
grade errors 63
threshold crossings 64
```

More rows therefore did not automatically improve the target-domain model. Before considering any reweighting or resampling, Nongtori audits train-only distribution shift across weight, width, height, grade, variety and source sheet.

Command:

```bash
python -m ml.weight_baseline.geometry_auxiliary_shift_audit_v1
```

Validation/test are not used to diagnose or select the shift-handling strategy.

## 13. Geometry V3 reweighted auxiliary experiment

The auxiliary shift audit found a material train-domain difference:

- auxiliary mean weight is +2.3651g higher than strict train;
- auxiliary mean width is +1.3844mm higher;
- auxiliary mean height is +2.0768mm higher;
- grade-distribution total-variation distance is 0.1542.

Therefore Geometry V3 does not concatenate all auxiliary rows at equal weight. It keeps the rows but matches their effective grade mass to the strict fold-train grade distribution.

Fixed candidates:

```text
STRICT_ONLY
GRADE_MATCHED_AUX_025
GRADE_MATCHED_AUX_050
GRADE_MATCHED_AUX_100
```

Candidate selection is official-train 5-fold OOF only. Official validation 79 is confirmation only and official test 78 remains locked.

Command:

```bash
python -m ml.weight_baseline.geometry_v003
```

## 14. Cohort compatibility gate before reweighting

Geometry V3 is not automatically approved merely because the auxiliary cohort has a different grade distribution.

Reweighting is `HOLD_PENDING_MANUAL_COMPATIBILITY_REVIEW` until the strict-train and auxiliary cohorts are compared without changing any source values.

Required diagnostics:

- variety composition
- source-sheet composition
- photo availability selection (`YES` / `NO`)
- weight / width / height / width×height distributions
- area↔weight correlation
- strict-model → auxiliary transfer metrics
- auxiliary-model → strict-train transfer metrics
- shared-variety cross-cohort residual behavior

The audit verifies every auxiliary weight/width/height and metadata field against the canonical Dryad datasheet. Any mismatch fails closed.

Command:

```bash
python -m ml.weight_baseline.geometry_cohort_compatibility_audit_v1
```

`geometry_v003` is blocked by default and may run only after explicit compatibility review:

```bash
python -m ml.weight_baseline.geometry_v003 --allow-after-compatibility-review
```

This flag is an acknowledgement of review, not proof that reweighting is valid.

## 15. Portfolio completion boundary

Weight Estimation V1의 목표는 학술적으로 가능한 모든 개선을 끝까지 구현하는 것이 아니다.

V1 완료 범위:

```text
Geometry baseline
→ RGB baseline
→ paired residual
→ Fusion V001
→ Fusion boundary residual audit
→ validation-based selective AUTO_GRADE / RE_MEASURE_REQUIRED policy
→ ML V1 freeze
```

완료 후 우선순위는 모델 반복 연구가 아니라 다음 제품 연결이다.

- runtime weight provenance
- measured fallback
- grade/quality decision flow
- API/UI integration
- mobile/field UX
- QA / acceptance evidence

전체 과실 99% grade accuracy는 V1 hard requirement가 아니다. 대신 자동확정된 subset에 대해 높은 precision을 확보하면서 coverage와 fallback burden을 함께 보고한다.

다음은 successor research / FUTURE로 분리한다.

- RGB-D / stereo / 3D volume reconstruction
- 대규모 품종·농가·계절 데이터 확대
- boundary-aware multi-task / ordinal learning 반복 연구
- deep ensemble / probabilistic regression / conformal prediction
- 품종·장비별 calibration
- 실제 load-cell과 vision의 sensor-fusion 비교
- 독립 field holdout을 이용한 production-grade validation

이 구분은 연구 가능성을 부정하는 것이 아니라, 개인 기업용 포트폴리오 V1의 완료 시점을 통제하기 위한 scope 결정이다.

## 16. Hardware integration rule

Future adapter boundary:

```text
HarvestDeviceAdapter
    ├─ measured weight available
    │      → SENSOR_MEASURED
    │
    └─ measured weight unavailable
           → VisionWeightEstimator
              → VISION_ESTIMATED
```

This keeps the core grading service independent from hardware details and avoids redesigning the product if the selected robot later exposes a load-cell measurement.
