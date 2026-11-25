# 농산물 시세 예측 모듈

이 폴더는 오프라인 가격 백테스트와 CatBoost·TFT 학습 후보를 제공한다. 운영 모델은 검증된 시세 데이터 적재, 시간순 성능 평가, 운영 승인, `forecast_model_registry` 등록을 거친다.

## Track C 가격 기준선 백테스트

```bash
python -m ml.price_forecast.baseline --data prices.csv \
  --start 2026-01-01 --end 2026-02-28 --labels-as-of 2026-03-15T00:00:00+09:00 \
  --horizon-days 1 --window 7 --seasonal-period-days 7
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

정답은 `--labels-as-of`까지의 최신 관측으로 고정한다. 최근가와 이동평균은 이동평균 이력과 실제값이 모두 있는 같은 날짜에서 MAE, RMSE, sMAPE, WAPE를 비교한다. `seasonal_comparison`은 정확히 N일 전 거래의 가용 가격이 있는 날에 세 기준선을 함께 계산하며, 그중 계절 이력이 없는 일수를 따로 집계한다. 보고서에는 입력 해시, 버전 중복·가용 시각 제외 수, 시계열별 평가·실제값 누락·철회·이력 부족 일수가 포함된다. 실제값 누락에는 휴장과 자료 누락이 함께 포함될 수 있다.

## 공급자 계약과 수집 조건

- aT의 `GET /B552845/katOrigin/trades`는 정산일·도매시장 조회 및 `pageNo`·`numOfRows` 페이지를 제공한다. 시장·법인·품목 분류·산지·단위·포장·등급은 제공자의 표준코드를 따른다. 포털에는 무료, 이용허락 제한 없음, 활용 신청 후 자동승인, 개발계정 신청 가능 트래픽 10,000으로 게시돼 있다. 실제 수집 전 적용 계정의 권한과 일일·초당 한도, 이력 조회 범위를 확인한다. [aT 경매원천정보](https://www.data.go.kr/data/15141810/openapi.do?recommendDataYn=Y) · [aT 표준코드](https://www.data.go.kr/data/15141818/openapi.do)
- 농식품부 명세는 거래 단량·포장·수량·단가·총금액을 개별 필드로 제공한다. 단위 코드 `11`은 g, `12`는 kg, `13`은 톤이다. 거래일과 정산일의 구분, 페이지 일관성, 산지·품종 매핑, 정정·철회 식별자와 원천 버전의 공개 시각은 실제 응답과 제공기관 근거로 확인한다. 원본을 최초로 수신한 시각은 해당 버전을 그 시각부터 사용할 수 있었다는 증거로 쓴다. 과거 거래일·정산일로 공개 시각을 소급하지 않는다. [농식품부 경매 필드 정의](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20240625000000002462) · [단위 코드 계약](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20240626000000002472)
- KAMIS 최근 가격은 중도매인·소매 조사 가격이며, 농정원 API는 도매시장 목록이다. 경매 거래 가격과 구분한다. [KAMIS 최근 가격](https://www.data.go.kr/data/15156063/openapi.do) · [농정원 시장 목록](https://www.data.go.kr/data/15109237/openapi.do)
- aT 페이지 응답의 구조는 성공 코드, 요청 좌표, 전체 건수, 페이지별 수량, 페이지 간 중복과 요청 범위로 확인한다. 공급자가 페이지를 읽는 동안 동일한 판본을 보장하는지는 실제 응답 및 계약에서 추가 확인해야 한다. 원표·경매 순번 조합의 고유성, `scsbd_dt`의 형식과 시간대 역시 실제 확인 대상이다. 현재 오프셋이 없는 낙찰 일시는 KST로 해석하며 공란과 잘못된 시각은 제외 근거로 기록한다. [공개 카탈로그 응답 필드](https://gongapi.kr/d/15141810) · [필드 관측 사례](https://labs.ai.bigvalue.co.kr/data/d/15141810)

### 실제 수집과 재사용

개발 환경의 `NONGTORI_AT_SERVICE_KEY`에 승인된 키를 설정한다. 공공데이터포털이 발급한 디코딩 키를 사용한다. `codes.json`의 `evidence_sha256`은 검토한 표준코드 원본 또는 원본별 해시 매니페스트와 일치해야 한다. 그 근거에서 아래 항목을 추출해 저장한다. 표준코드 숫자는 모두 문자열로 보존한다.

| 항목 | 형식 |
| --- | --- |
| `markets,origins,grades,packages,sizes,units` | 코드 문자열 배열 |
| `corporations` | `[시장 코드, 법인 코드]` 배열 |
| `products` | `[대분류, 중분류, 소분류]` 배열. 설향 이름과 코드의 대응을 표준코드 원본에서 확인한다. |

같은 코드 참조로 재생할 수 있도록 원본, 매니페스트, 정규화한 코드 참조를 함께 보관한다. 아카이브와 결과에는 코드 참조, 어댑터 버전, 원본 페이지 해시를 기록한다. 아래 명령의 경로·코드·호출 한도 변수는 실행 환경에서 확인한 값을 사용한다.

```bash
python -m ml.price_forecast.auction_archive \
  --archive "$AT_ARCHIVE" --codebook "$AT_CODEBOOK" --code-evidence "$AT_CODE_EVIDENCE" collect \
  --settlement-day "$AT_SETTLEMENT_DAY" --market "$AT_MARKET" \
  --category "$AT_CATEGORY" --product "$AT_PRODUCT" --cultivar "$AT_CULTIVAR" \
  --max-pages "$AT_APPROVED_PAGES" --interval-seconds "$AT_APPROVED_INTERVAL"

python -m ml.price_forecast.auction_archive \
  --archive "$AT_ARCHIVE" --codebook "$AT_CODEBOOK" --code-evidence "$AT_CODE_EVIDENCE" inspect

python -m ml.price_forecast.auction_archive \
  --archive "$AT_ARCHIVE" --codebook "$AT_CODEBOOK" --code-evidence "$AT_CODE_EVIDENCE" export \
  --category "$AT_CATEGORY" --product "$AT_PRODUCT" --cultivar "$AT_CULTIVAR" \
  --output "$AT_DAILY_CSV" > "$AT_DATA_REPORT"
```

완전히 저장된 동일 요청은 재사용한다. `--refresh`로 다시 조회할 때 새 원본만 별도 버전으로 보관한다. 원본은 제한된 로컬 경로의 SQLite에 보관하며 수집 기록과 함께 Git에 올리지 않는다. 요청 범위가 겹치는 수집본은 중복 집계를 막기 위해 일별 내보내기가 중단된다. 변경 행이 사라지면 독립적으로 확인한 철회 증빙을 연결해 재생한다. `export --withdrawals`가 받는 JSON 배열의 각 항목은 `query`(필터의 원래 aT 필드), `edition_sha256`, `trade_id`, `observed_at`, `source_sha256`, `evidence_file`을 가진다. 같은 원본 해시가 다시 나타났을 때 `edition_available_at`으로 판본을 지정할 수 있다.

kg 코드의 거래 단량×수량과 거래 중량, 단위당 낙찰가×수량과 총금액이 각각 일치해야 한다. 다른 질량 단위는 aT의 합계 필드 기준을 확인한 뒤 추가한다. 일별 가용 시각은 완전 수집본을 확인한 시각이며, 늦게 확인된 철회는 증빙 시각까지 반영을 보류한다. 과거 자료를 지금 내려받으면 이전 예측 시점에 공개됐다는 근거가 되지 않는다. 실측 평가 전에 대상 시장·법인과 수집일을 확인하고, 내보내기의 산지·등급별 관측 및 제외 결과와 파일 해시를 보존한다.

## 수확 매출 연계 계약

향후 연계의 입력은 수확 예정일, 예상 수확량 kg, 품종·등급·판매 용도별 시계열 키 및 해당 거래일의 예측 KRW/kg이다. 일반 판매와 잼용에는 각 용도에 확인된 등급·가격 시계열을 연결한다. 예상 총매출은 각 판매 등급의 예상 수확량과 단가를 곱한 값의 합이다. P10/P50/P90처럼 검증된 단가 범위가 있으면 매출 시나리오를 표시할 수 있다. 등급별 하한·상한을 단순 합산한 범위는 결합 매출의 보정된 분위수로 해석하지 않는다. 기준선은 점예측을 제공한다. 실제 정산액과 운송·수수료 등 비용은 별도 계약을 따른다. 공유 API·UI 구현은 해당 담당과 조정한다.

합성 매출 fixture는 실제 forecast worker의 claim/PUT 필드와 g→kg 환산을 사용해 일반 판매와 잼용 가격을 별도로 검증한다. 예상 총매출과 시나리오 범위를 계산하고 실정산은 빈 값으로 둔다. [합성 매출 fixture](../../tests/fixtures/price_revenue_synthetic.json)

## 학습 후보 입력 검증

```bash
python -m ml.price_forecast.train_catboost --data "$AT_DAILY_CSV" \
  --input-sha256 "$AT_VERIFIED_CSV_SHA256" --labels-as-of "$AT_LABEL_CUTOFF"
python -m ml.price_forecast.train_tft --data "$AT_DAILY_CSV" \
  --input-sha256 "$AT_VERIFIED_CSV_SHA256" --labels-as-of "$AT_LABEL_CUTOFF"
```

기본 실행은 고정한 CSV와 시간순 학습·모델 선택 검증·holdout 분할을 확인한다. 후보 학습은 적격 판정 이후 `--train --output <폴더>`로 명시한다. CatBoost는 시계열 키·달력·이전 관측일 가격만 사용한다. TFT는 이전 가격을 인코더에, 미리 계산 가능한 달력을 디코더에 사용한다. 두 후보는 당일 거래량·실측 기상·원본 메타데이터를 특징에서 제외한다. 현 학습 경로는 KST 거래일 내 실제 가용했던 단일 가격 버전만 받고, TFT는 시계열 거래일 공백을 거부한다. 늦게 확보한 버전과 정정·철회 이력은 백테스트에서 별도로 평가할 수 있다. 모델 선택용 조기 종료 지표와 독립 holdout 성능 기록은 별개다.

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
