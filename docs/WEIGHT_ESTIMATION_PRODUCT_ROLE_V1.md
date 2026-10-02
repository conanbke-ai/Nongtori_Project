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

## 9. Hardware integration rule

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
