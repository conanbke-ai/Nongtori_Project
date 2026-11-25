# 농산물 시세 예측 모듈

이 폴더는 오프라인 가격 백테스트와 CatBoost·TFT 학습 후보를 제공한다. 운영 모델은 검증된 시세 데이터 적재, 시간순 성능 평가, 운영 승인, `forecast_model_registry` 등록을 거친다.

## Track C 가격 기준선 백테스트

```bash
python -m ml.price_forecast.baseline --data prices.csv \
  --start 2026-01-01 --end 2026-02-28 --labels-as-of 2026-03-15T00:00:00+09:00 \
  --horizon-days 1 --window 7
```

저장소 루트에서 실행한다. 입력은 출처와 버전별 가용 시각이 검증된 UTF-8 일별 CSV다. 열 이름은 다음과 같다.

| 열 | 의미 |
| --- | --- |
| `provider,market,corporation,product,origin,cultivar,grade,unit` | 전체 시계열 키. `provider`는 제공기관과 데이터셋을 식별한다. `unit`은 단위 코드·단량·포장·필요한 규격까지 구별한다. 선행 0을 유지하며 모든 키가 일치할 때만 같은 시계열로 본다. |
| `trade_day` | 실제 거래일 `YYYY-MM-DD`. 정산일은 원천 조회 키와 provenance에 따로 둔다. |
| `available_at,source_sha256` | 해당 버전이 실제로 이용 가능했다는 근거의 시각(UTC 오프셋 포함)과 SHA-256. 해시는 별도 보관하는 원본 또는 원본별 해시가 있는 매니페스트를 식별한다. |
| `status,price_krw_per_kg,trade_volume_kg` | `TRADED`에는 검증된 원/kg 단가와 양수 kg 거래량을 넣는다. 원천 근거로 확인한 일별 관측 철회는 `WITHDRAWN`과 두 숫자 열 공란으로 기록한다. |

원천은 거래 단위당 가격, 포장, 단량, 수량과 출처를 보존한다. 정규화 단계에서 확인된 순중량으로 kg를 환산하며, 일별 평균을 만들 경우 동일 키의 총 거래금액을 총 거래중량으로 나눈다. 박스당 가격을 `price_krw_per_kg`에 넣거나 산지·품종·등급·포장 규격을 합치지 않는다. 데이터 수집·일별 정규화·원본 해시 검증은 이 CLI의 입력을 만드는 별도 단계다.

평가 구간은 날짜 양끝을 포함한다. `--horizon-days 1`이면 대상 거래일 직전 KST 자정 미만에 이용 가능했던 이전 거래일만 예측에 사용한다. 3일이면 대상일 3일 전 하루가 끝날 때까지의 자료를 사용한다. 각 시점에 보였던 정정본으로 최근가와 최근 N개 관측일 이동평균을 계산한다. 같은 시각·같은 날짜에 가격 또는 물량이 상충하면 평가를 중단한다. 원천이 명시적으로 철회한 관측은 그 철회 시각 이후 이력에서 제외한다.

정답은 `--labels-as-of`까지의 최신 관측으로 고정한다. 두 기준선은 이동평균에 필요한 이력과 실제값이 모두 있는 같은 날짜에서 MAE, RMSE, sMAPE, WAPE를 비교한다. 보고서에는 입력 해시, 버전 중복·가용 시각 제외 수, 시계열별 평가·실제값 누락·철회·이력 부족 일수를 포함한다. 실제값 누락에는 휴장과 데이터 누락이 함께 포함될 수 있다. 결과는 가용 시각이 검증된 데이터의 성능만 나타내며, 계절성·공급량·거래일 요인과 복합 모델의 개선 평가는 동일한 holdout을 사용한다.

## 공급자 계약과 수집 조건

- aT의 `GET /B552845/katOrigin/trades`는 정산일·도매시장 조회 및 `pageNo`·`numOfRows` 페이지를 제공한다. 시장·법인·품목 분류·산지·단위·포장·등급은 제공자의 표준코드를 따른다. 포털에는 무료, 이용허락 제한 없음, 활용 신청 후 자동승인, 개발계정 신청 가능 트래픽 10,000으로 게시돼 있다. 실제 수집 전 적용 계정의 권한과 일일·초당 한도, 이력 조회 범위를 확인한다. [aT 경매원천정보](https://www.data.go.kr/data/15141810/openapi.do?recommendDataYn=Y) · [aT 표준코드](https://www.data.go.kr/data/15141818/openapi.do)
- 농식품부 명세는 거래 단량·포장·수량·단가·총금액을 개별 필드로 제공한다. 단위 코드 `11`은 g, `12`는 kg, `13`은 톤이다. 거래일과 정산일의 구분, 페이지 일관성, 산지·품종 매핑, 정정·철회 식별자와 원천 버전의 공개 시각은 실제 응답과 제공기관 근거로 확인한다. 원본을 최초로 수신한 시각은 해당 버전을 그 시각부터 사용할 수 있었다는 증거로 쓴다. 과거 거래일·정산일로 공개 시각을 소급하지 않는다. [농식품부 경매 필드 정의](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20240625000000002462) · [단위 코드 계약](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20240626000000002472)
- KAMIS 최근 가격은 중도매인·소매 조사 가격이며, 농정원 API는 도매시장 목록이다. 경매 거래 가격과 구분한다. [KAMIS 최근 가격](https://www.data.go.kr/data/15156063/openapi.do) · [농정원 시장 목록](https://www.data.go.kr/data/15109237/openapi.do)
- 기존 증분 플래너는 동일 요청의 검증된 수집 기록을 재사용한다. 페이지 전체와 요청 범위를 확인해 원본을 해시로 보관하고, 관측의 중복·정정 버전을 관리하는 실제 수집기는 연결하기 전 별도로 검증한다.

## 수확 매출 연계 계약

향후 연계의 입력은 수확 예정일, 예상 수확량 kg, 품종·등급·판매 용도별 시계열 키 및 해당 거래일의 예측 KRW/kg이다. 일반 판매와 잼용에는 각 용도에 확인된 등급·가격 시계열을 연결한다. 예상 총매출은 각 판매 등급의 예상 수확량과 단가를 곱한 값의 합이다. P10/P50/P90처럼 검증된 단가 범위가 있으면 매출 시나리오를 표시할 수 있다. 등급별 하한·상한을 단순 합산한 범위는 결합 매출의 보정된 분위수로 해석하지 않는다. 기준선은 점예측을 제공한다. 실제 정산액과 운송·수수료 등 비용은 별도 계약을 따른다. 공유 API·UI 구현은 해당 담당과 조정한다.

## 채택 구조

1. **초기·희소 데이터: CatBoost 분위수 회귀**
   - 가격 lag, 이동평균, 달력, 거래량, 시장·작물·품종·등급·포장단위를 사용한다.
   - P10/P50/P90을 별도 학습해 단일 금액 대신 범위를 제공한다.
   - 범주형 변수가 많고 품종별 데이터가 적은 초기 단계의 비교 후보다.
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

위 스키마는 기존 CatBoost·TFT 학습 후보 전용이다. 운영 비교 전에 산지·법인·출처 키와 시점별 가용성 보존을 검증해야 한다. CatBoost의 입력 자동 선택은 당일 거래량 등 예측 시점에 이용할 수 없는 열을 포함할 수 있어 후보 성능의 근거로 사용하려면 입력 명세와 평가를 보완해야 한다.

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
