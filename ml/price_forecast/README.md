# 농산물 시세 예측 모듈

이 폴더는 아직 학습되지 않은 **실행 가능한 기준 구현**이다. 실제 모델이라고 표시하려면 KAMIS·도매시장 데이터 적재, 시간순 검증, 운영 승인, `forecast_model_registry` 등록까지 완료해야 한다.

## 채택 구조

1. **초기·희소 데이터: CatBoost 분위수 회귀**
   - 가격 lag, 이동평균, 달력, 거래량, 시장·작물·품종·등급·포장단위를 사용한다.
   - P10/P50/P90을 별도 학습해 단일 금액 대신 범위를 제공한다.
   - 범주형 변수가 많고 품종별 데이터가 아직 적은 초기 단계의 운영 기준 모델이다.
2. **데이터 누적 후: Temporal Fusion Transformer(TFT)**
   - 시장·작물·품종·등급을 하나의 글로벌 다중 시계열로 학습한다.
   - 정적 변수, 미래에 아는 달력 변수, 관측 가격·거래량·기상 변수를 구분한다.
   - 1·3·7일 다중 시점 분위수 예측과 변수 중요도 해석에 사용한다.
3. **운영 모델 선택**
   - 무작위 분할을 사용하지 않는다. rolling-origin 검증에서 seasonal-naive/CatBoost/TFT를 동일 기간으로 비교한다.
   - P50 MAE·sMAPE, P10/P50/P90 pinball loss, P10–P90 포함률을 함께 본다.
   - 작물·등급별 검증 결과가 더 나은 모델만 `ACTIVE`로 승격한다. TFT를 무조건 채택하지 않는다.

## 입력 스키마

필수: `date`, `market_code`, `crop_code`, `cultivar_code`, `grade_code`, `package_unit`, `price_per_kg`.

권장: `trade_volume_kg`, `temperature_mean_c`, `precipitation_mm`, `humidity_mean_pct`, `is_holiday`. 가격은 포장단위 원가를 그대로 섞지 말고 `원/kg`으로 정규화해야 한다.

## 실행

```bash
python -m venv .venv
pip install -r requirements.txt
python train_catboost.py --data data/prices.parquet --output artifacts/catboost-v1
python train_tft.py --data data/prices.parquet --output artifacts/tft-v1
```

수확 완료 API는 `forecast_jobs`에 자동 작업을 넣는다. 별도 예측 작업자가 `/api/forecast-worker`에서 작업을 claim하고, 운영 승인된 모델로 등급별 P10/P50/P90 단가를 계산한 뒤 같은 API의 `PUT`으로 결과를 저장한다. 농민 화면에는 입력란이 없고 저장된 결과만 표시된다.

## 근거 자료

- Lim et al., *Temporal Fusion Transformers for Interpretable Multi-horizon Time Series Forecasting*, International Journal of Forecasting (2021): https://doi.org/10.1016/j.ijforecast.2021.03.012
- DCS 2025 국내 농산물 가격 TFT 적용 연구: https://doi.org/10.9728/dcs.2025.26.3.821
- Prokhorenkova et al., *CatBoost: unbiased boosting with categorical features*, NeurIPS (2018): https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html
- Nie et al., *A Time Series is Worth 64 Words: Long-term Forecasting with Transformers*, ICLR (2023): https://openreview.net/forum?id=Jbdc0vTOcol
- Oreshkin et al., *N-BEATS*, ICLR (2020): https://openreview.net/forum?id=r1ecqn4YwB
- KAMIS 농산물 가격정보 API: https://www.data.go.kr/data/15156063/openapi.do
- 전국 도매시장 실시간 경매정보 API: https://www.data.go.kr/data/15109237/openapi.do

논문 모델은 후보 선정의 근거이며, 설향·등급별 실제 성능을 보장하지 않는다. 운영 채택 여부는 국내 데이터로 재검증한다.
