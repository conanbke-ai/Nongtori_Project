# Nongtori Market Price & Settlement Estimation Policy

## 1. 목적

가격 기능은 설향 전용 가격표가 아니라 품목/품종/시장/법인/등급/규격을 처리하는 범용 시장가격 모듈이다. 첫 검증 대상은 딸기 설향이다.

출력:

- 예상 낙찰단가 `KRW/kg`
- 예상 정산 거래액

실제 농가 실정산 자료가 없는 동안 `실제 정산액`, `실수령액`이라고 표현하지 않는다.

## 2. 계산

```text
예상 정산 거래액 = 실제 수확량(kg) × 예상 낙찰단가(KRW/kg)
```

운송비, 수수료, 포장비, 조정금 등 실제 비용이 확인되지 않은 상태에서는 임의 공제하지 않는다.

## 3. 원본/정규화

원본 시장 데이터의 가격, 거래단위, 포장단위, 시장/법인, 품목/품종, 등급/규격을 보존한다. 정규화 계층에서만 `KRW/kg`로 변환한다.

unit/package mapping이 불명확하면 `UNIT_NORMALIZATION_ERROR`로 처리하고 추정 단가를 만들지 않는다.

## 4. 날짜 의미

```yaml
source_harvest_date: YYYY-MM-DD | null
scenario_date: YYYY-MM-DD
```

- `source_harvest_date`: Sheet 원래 날짜. provenance다.
- `scenario_date`: 예측/백테스트 대상일.

`SCENARIO_BACKTEST`에서는 현장 수확량/등급/규격 record를 재사용할 수 있지만 모든 달력/시계열 feature는 `scenario_date` 기준으로 구성한다.

## 5. Leakage 금지

`scenario_date=D` 예측에는 D 시점 전에 이용 가능했어야 하는 정보만 사용한다. D의 실제 시장가격은 모델 input이 아니라 사후 평가용 `ACTUAL_MARKET_REFERENCE`다.

금지:
- 당일 실제 가격을 input에 포함
- 미래 이동평균/집계값
- random train/test split
- source_harvest_date를 scenario date처럼 사용

가격 split은 chronological split을 사용한다.

## 6. 모드

- `LIVE_FORECAST`: 현재/미래 거래일 예측
- `HOLDOUT_BACKTEST`: 고정 과거 holdout 기간 공식 평가
- `SCENARIO_BACKTEST`: 사용자가 임의 과거 날짜를 지정해 시나리오 재생

공식 모델 성능은 `HOLDOUT_BACKTEST`에서 산출하고, 시나리오 모드는 설명/재현용으로 분리한다.

## 7. Failure status

- `NO_MARKET_TRADE`
- `UNSUPPORTED_ITEM`
- `VARIETY_MAPPING_ERROR`
- `UNIT_NORMALIZATION_ERROR`
- `SOURCE_UNAVAILABLE`
- `MODEL_UNAVAILABLE`
- `OUT_OF_DISTRIBUTION`

실패를 가짜 예상가로 덮지 않는다.

## 8. Model candidate / metric

초기 후보는 단순 seasonal/rolling baseline과 tree-based model(XGBoost/CatBoost 등)을 먼저 비교한다. 복잡한 시계열 모델은 데이터량과 개선 근거가 있을 때 승격한다.

평가:
- MAE
- RMSE
- sMAPE
- WAPE
- 예상 거래액 오차

모델 acceptance는 `MODEL_ACCEPTANCE_POLICY.md`를 따른다.
