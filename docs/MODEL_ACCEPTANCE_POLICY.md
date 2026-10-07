# Nongtori Model Acceptance Policy

## 1. 원칙

데이터와 baseline을 보기 전에 `accuracy 90% 이상` 같은 임의 숫자를 완료 조건으로 만들지 않는다.

Acceptance는 다음 세 축으로 결정한다.

```text
1. Baseline 대비 개선
2. 업무에 맞는 primary / operational metric
3. 독립 test / field validation
```

## 2. 상태

- `REFERENCE`
- `REPRODUCED`
- `CANDIDATE`
- `VALIDATED`
- `FIELD_VALIDATED`
- `REJECTED`

논문 reported metric을 곧바로 Nongtori `VALIDATED`로 표시하지 않는다.

## 3. 공통 Gate

후보 승격 전에:

- immutable snapshot/split manifest 고정
- source/model provenance 기록
- baseline 동일 split 평가
- test set tuning 금지
- metric artifact/seed/config 기록
- 실패 class/edge case 분석
- field validation은 별도 표기

## 4. Detection

- mAP50
- mAP50-95
- Precision
- Recall
- small/occluded fruit recall

## 5. Ripeness

- Macro F1
- Confusion Matrix
- Ordinal MAE
- Weighted Kappa
- single-frame vs multi-frame 비교

숙도는 순서형 label이므로 단순 accuracy만 보지 않는다.

## 6. Quality / Grade

- Macro F1
- class별 Precision/Recall/F1
- Confusion Matrix
- JM false acceptance / false rejection

JM 내부 subtype을 데이터 근거 없이 임의 세분화해 official metric으로 주장하지 않는다.

## 7. Weight Estimation

Weight Estimation은 전체 과실에 대한 단일 Accuracy 숫자만으로 acceptance를 결정하지 않는다.

필수 regression metric:

- MAE
- RMSE
- R²
- bias
- max absolute error

필수 operational metric:

- 12 / 16 / 22 g threshold crossing
- weight-grade accuracy / confusion
- severe grade error
- boundary distance band별 오류
- selective auto-grade precision
- auto-grade coverage
- re-measure / fallback rate

raw model confidence가 0.99라는 이유만으로 실제 99% 정확도로 해석하지 않는다. 자동확정 정책에 confidence를 사용할 경우 validation에서 calibration된 확률 또는 검증된 uncertainty/boundary-risk 기준이어야 한다.

포트폴리오 V1은 전체 과실 99% grade accuracy를 사전 hard gate로 두지 않는다. 대신 다음 trade-off를 명시적으로 측정한다.

```text
AUTO_GRADE precision
×
AUTO_GRADE coverage
×
fallback burden
```

높은 precision을 얻기 위해 대부분의 과실을 재측정으로 보내는 정책도 제품 acceptance에 실패할 수 있다.

현재 개발 순서:

```text
Geometry
→ RGB
→ paired residual
→ Fusion
→ Fusion boundary residual audit
→ selective auto-grade / re-measure policy
→ Weight ML V1 freeze
```

multi-task/ordinal, RGB-D/3D, probabilistic/conformal uncertainty, 대규모 외부 field validation은 V1 완료를 무기한 미루지 않도록 별도 successor research scope로 관리한다.

## 8. Tracking

ByteTrack/BoT-SORT 등을 동일 video set에서 비교한다.

- ID Switch
- Fragmentation
- Unique Fruit Count Error
- Missed Unique Fruits
- Duplicate Count
- HOTA / IDF1
- FPS
- VRAM

최종 선택은 tracking 안정성 + inference 정확도 + 운영자원 trade-off로 결정한다.

## 9. Pest

- Recall
- Precision
- F1
- PR-AUC
- false alerts / zone

병해충은 미탐 비용과 과도한 현장 확인 비용을 함께 본다.

## 10. Price

- MAE
- RMSE
- sMAPE
- WAPE
- 예상 거래액 오차

chronological holdout에서 평가한다.

## 11. Field validation

`VALIDATED`와 `FIELD_VALIDATED`를 구분한다. field set을 tuning에 사용했다면 새로운 독립 field holdout이 필요하다.
