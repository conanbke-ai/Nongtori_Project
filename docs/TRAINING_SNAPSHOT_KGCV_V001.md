# KGCV Ripeness Training Snapshot v001

Status: **FROZEN / EXTERNAL REFERENCE SNAPSHOT**

Snapshot ID: `KGCV-RIPENESS-V001`

## Purpose

Nongtori 숙도 모델의 첫 reproducible external baseline을 만들기 위한 고정 데이터셋이다. 이 snapshot은 KGCV 외부 데이터만 포함하며 현장 데이터의 `FIELD_TEST` 지위를 대체하지 않는다.

## Frozen identity

- Source: `DATA-RIP-002` / `Project-AgML/strawberry_growth_detection`
- Mapping: `MAP-RIP-002-v2`
- Candidate manifest SHA-256: `4a99618d7024a960f4f2431b17feaca2088415c2d14149be859df758f8985b9f`
- Physical images hash-verified: 1,477 / 1,477
- Unique SHA-256: 1,477
- Byte-identical duplicate groups: 0
- Hash errors: 0
- Object rows audited: 3,997
- Snapshot-eligible rows: 3,162

## Included labels

| KGCV label | Nongtori Maturity | Count |
|---|---:|---:|
| small g | 0 | 673 |
| green | 0 | 898 |
| white | 1 | 731 |
| red | 4 | 669 |
| overripe | 4 | 191 |

Total maturity distribution:

- Maturity 0: 1,571
- Maturity 1: 731
- Maturity 4: 860

## Explicit exclusions

- `flower`: 539 — `NON_FRUIT_RIPENESS_TARGET`
- `turning red`: 296 — `UNRESOLVED_TURNING_BOUNDARY`

`turning red`의 decimal-stage 관측값만 보고 임의 threshold를 만들어 Maturity 2/3으로 편입하지 않는다. Field calibration 이후 새로운 mapping version + 새로운 snapshot으로만 편입한다. v001은 수정하지 않는다.

## Frozen split

Split seed: `20260910`

Atomicity:

1. 같은 physical image의 모든 object는 동일 split
2. 동일 SHA-256 asset은 동일 split
3. test는 tuning에 사용하지 않음

| Split | Samples | M0 | M1 | M4 |
|---|---:|---:|---:|---:|
| train | 2,243 | 1,125 | 517 | 601 |
| valid | 486 | 250 | 111 | 125 |
| test | 433 | 196 | 103 | 134 |

## Baseline contract

Config: `configs/ripeness-baseline-v001.json`

첫 baseline은 복잡한 architecture 경쟁이 아니라 재현 가능한 기준선 확보가 목적이다.

- ResNet-18 ImageNet transfer-learning reference
- object crop classification
- input 224×224
- primary metrics: Macro F1, Ordinal MAE, Weighted Kappa
- secondary: accuracy, per-class P/R/F1, confusion matrix
- validation으로 early stopping/model selection
- test는 configuration freeze 후 최종 1회 평가

Baseline 결과를 보기 전에 임의 목표 정확도를 설정하지 않는다.

## Status semantics

Snapshot이 FROZEN이라는 것은 데이터/split identity가 고정됐다는 의미다. 모델이 `VALIDATED` 또는 `FIELD_VALIDATED`라는 의미가 아니다.

Baseline 첫 성공 run은 `REFERENCE → REPRODUCED` 승격 후보이며, 현장 독립 holdout 검증 전에는 `FIELD_VALIDATED`를 사용할 수 없다.

## Future snapshot rule

다음 변경은 v001을 수정하지 않고 v002+로 만든다.

- turning-red Maturity 2/3 calibration 반영
- Nongtori field training rows 편입
- 다른 approved external source 추가
- label mapping version 변경
- split policy 변경
