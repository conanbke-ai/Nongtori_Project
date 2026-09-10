# Nongtori Data Split & Leakage Policy

## 1. 공통 원칙

1. test set은 모델 선택/Optuna/threshold 조정에 사용하지 않는다.
2. 동일 실제 개체/연속 frame/sequence가 split을 넘지 않는다.
3. public data와 field data의 역할을 분리한다.
4. split 전에 duplicate/near-duplicate audit를 한다.
5. official metric은 immutable split manifest에서만 산출한다.

## 2. 사진

`Group_ID`는 동일 딸기의 F/RT45 등 다각도 관측 묶음이다.

**동일 Group_ID는 반드시 같은 split**에 둔다. row random split을 금지한다.

또한 동일 시간대/Zone의 연속 촬영은 배경/조명 leakage 가능성을 audit한다.

## 3. 영상

- 동일 video는 하나의 split
- 동일 capture/scan session은 하나의 split
- 동일 fruit track cross-split 금지
- extraction frame을 무작위 row split하지 않음

## 4. Field / Public

권장 역할:

```text
PUBLIC_TRAIN
PUBLIC_VALID
PUBLIC_TEST
FIELD_TRAIN(optional)
FIELD_VALID(optional)
FIELD_TEST
```

`FIELD_TEST`는 독립 평가용이다. tuning/fine-tuning/threshold 조정에 사용했다면 더 이상 pristine field holdout으로 부르지 않는다.

## 5. Task eligibility

같은 row라도 task별 eligibility가 다를 수 있다.

예:
- `Grade=JM` + Weight NULL → grade task 가능, weight regression 불가
- Maturity 존재 + Grade NA → ripeness 가능, grade task 제외 가능

eligibility reason을 manifest에 기록한다.

## 6. 가격

가격은 chronological split을 사용한다.

`scenario_date=D`일 때 D 이후 데이터와 D 당일 실제 target price를 feature로 사용하지 않는다.

- train: 과거 구간
- validation: 그 다음 구간
- test/holdout: 가장 최근 독립 구간

rolling validation을 사용할 수 있지만 random split은 금지한다.

## 7. Split manifest

```yaml
split_id: RIPENESS_v001
snapshot_id: FIELD_PHOTO_v001
group_key: Group_ID
seed: ...
train: ...
validation: ...
test: ...
audit:
  cross_group_leakage: 0
  exact_duplicate_cross_split: 0
  near_duplicate_reviewed: true
```

영상/가격은 각 domain의 atomic key/cutoff를 함께 기록한다.

## 8. 금지

- 동일 Group_ID cross-split
- 동일 video/session cross-split
- test metric을 보고 Optuna 재조정
- field test를 반복 tuning 후 계속 field holdout이라고 부르기
- target date 이후 시장정보 사용
