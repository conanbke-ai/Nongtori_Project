# WEIGHT Fusion V001 Result — 2026-10-02

Status: **BENCHMARK_FROZEN / CURRENT_PREFERRED_WEIGHT_ESTIMATOR**

## 1. Selection result

Fusion family:

```text
fusion = alpha_rgb * RGB + (1 - alpha_rgb) * Geometry
```

Selection split:

```text
validation only
```

Selected weights:

```text
alpha_rgb      = 0.5
alpha_geometry = 0.5
```

Selection policy:

```text
VALIDATION_ONLY_LEXICOGRAPHIC_GRADE_CROSSING_MAE_RMSE
```

The frozen test split did not participate in alpha selection.

## 2. Validation result

| Model | MAE | RMSE | R² | Grade accuracy | Grade errors | Threshold crossings | MaxAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Geometry | 1.5291 g | 2.3288 g | 0.8395 | 73.42% | 21 | 21 | 12.9521 g |
| RGB | 1.5647 g | 2.3501 g | 0.8366 | 79.75% | 16 | 16 | 9.0073 g |
| **Fusion 0.5/0.5** | **1.2242 g** | **1.7285 g** | **0.9116** | **83.54%** | **13** | **13** | **5.8589 g** |

Validation threshold crossings for Fusion:

```text
12g: 0
16g: 6
22g: 7
total: 13
```

The selected blend improves all tracked validation regression metrics and operational grade metrics relative to both independent baselines.

## 3. Test result

| Model | MAE | RMSE | R² | Grade accuracy | Grade errors | Threshold crossings | MaxAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Geometry | 1.4125 g | 2.1850 g | 0.9003 | 82.05% | 14 | 15 | 8.8626 g |
| RGB | 1.2401 g | 2.3446 g | 0.8852 | 83.33% | 13 | 14 | 12.4082 g |
| **Fusion 0.5/0.5** | **0.9792 g** | **1.6143 g** | **0.9456** | **88.46%** | **9** | **10** | 9.3984 g |

Fusion test threshold crossings:

```text
12g: 4
16g: 5
22g: 1
total: 10
```

The already-selected validation blend remains stronger than both independent baselines on the frozen test split across:

- MAE
- RMSE
- R²
- bias magnitude
- grade accuracy
- grade-error count
- total threshold crossings

Fusion does not have the lowest individual-model MaxAE because one severe test outlier remains. This is retained as an explicit residual-risk item rather than hidden.

## 4. Current decision

Fusion V001 is frozen as the **current preferred vision weight estimator benchmark** for Nongtori.

This means:

```text
Current benchmark prediction
= 0.5 * RGB V001
+ 0.5 * Geometry V001
```

It does **not** mean:

- physical weighing is replaced by AI;
- test data may now be used for further fusion tuning;
- the model is field-production approved;
- the remaining 1–2g boundary risk is acceptable without further analysis.

Runtime source priority remains:

```text
SENSOR_MEASURED
→ MANUAL_MEASURED
→ VISION_ESTIMATED
```

A trusted measured weight still supersedes this model.

## 5. Test lock after V001

The frozen test split has now been used for the final V001 benchmark report.

From this point:

- do not tune alpha using test;
- do not tune 12/16/22g thresholds using test;
- do not select multi-task loss weights using test;
- do not select uncertainty bands using test;
- do not compare many successor variants repeatedly on this test split.

Successor development must use train + validation only until its experiment contract is frozen.

## 6. Required next gate: Fusion boundary residual audit

Before starting a new multi-task/ordinal model, audit the selected Fusion prediction around the fixed grade boundaries.

Command:

```bash
python -m ml.weight_baseline.audit_thresholds_v001 \
  --predictions artifacts/weight/fusion-v001/fusion_predictions.csv \
  --prediction-column fusion_pred_g \
  --output artifacts/weight/fusion-v001/threshold_residual_audit.json
```

Required questions:

1. Where are the remaining 9 test grade errors concentrated?
2. Which of 12 / 16 / 22g boundaries remains weakest?
3. How many errors occur within <=0.5g / <=1g / <=2g of a boundary?
4. Is the severe grade error an isolated outlier or part of a pattern?
5. Is a boundary-aware / ordinal auxiliary objective justified by validation residuals?

## 7. Portfolio interpretation

Fusion V001의 test MAE 약 0.98 g과 grade accuracy 약 88.46%는 독립 baseline보다 개선된 결과이지만, 현재 12/16/22 g 경계에서 완전자동 상용 선별기로 충분하다고 주장하지 않는다.

따라서 다음 제품 판단은 `전체 accuracy를 무조건 99%로 끌어올리는 것`이 아니라 다음 trade-off를 측정하는 것이다.

```text
AUTO_GRADE precision
×
AUTO_GRADE coverage
×
RE_MEASURE_REQUIRED rate
```

validation에서 정의한 안전영역만 AUTO_GRADE하고, 경계위험이 높은 과실은 실측 fallback으로 보낸다.

Fusion boundary residual audit와 selective policy가 고정되면 Weight ML V1은 freeze한다.

## 8. Successor experiment rule

A successor multi-task/ordinal experiment is justified only from **train/validation residual evidence**.

If pursued, its development evaluation should prioritize:

1. validation grade-error count;
2. validation threshold-crossing count;
3. validation boundary-band error rate;
4. validation MAE/RMSE;
5. severe-grade-error count.

The V001 test benchmark remains frozen as historical evidence and is not a tuning surface.
