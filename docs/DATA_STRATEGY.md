# Data Strategy

## 1. 상태와 원칙

```text
DESIGN / SCHEMA SEMANTICS → freeze 가능
SOURCE GOOGLE SHEET       → WORK_IN_PROGRESS
TRAINING DATASET          → versioned immutable snapshot만 사용
```

Google Sheet `딸기_프로젝트`는 현장 원본의 working canonical source다. 행 자체는 계속 수정/추가될 수 있으므로 live Sheet를 직접 학습 입력으로 사용하지 않는다.

## 2. 현재 canonical tabs

- `컬럼정보`
- `농가_딸기데이터`
- `농가_베드길이`

현재 실제 데이터 헤더는 다음 26개 필드다.

`Date`, `Time_Stamp`, `ID`, `Group_ID`, `Original_No`, `Weather`, `Farm`, `Zone`, `Variety`, `Class`, `DataType`, `View_Type`, `Occlusion`, `Length`, `Width`, `Weight_g`, `Maturity`, `Grade`, `Amb_Temp`, `Ref_Temp`, `Leaf_Temp`, `Amb_Humi`, `Light_Level`, `Health`, `Risk_Status`, `Final_Name`.

주요 코드:

- `Farm`: `M / C1 / C2 / U`
- `Variety`: 설향(`Sulhyang`) 중심
- `DataType`: `R / T / M / V`
- `Maturity`: `0 Green / 1 White / 2 Turning / 3 Mature / 4 Full`
- `Grade`: `SP / HI / MD / JM / NA`
- `Health`: `NOR / MIT / MIT_R / ANT / MAL / OTH`

## 3. Group_ID / multi-view

`Group_ID`는 동일 실제 딸기를 여러 시점으로 촬영한 묶음이다. `F`와 `RT45`는 정면 성능과 45도 성능을 별개 문제로 비교하기 위한 것이 아니라, 동일 과실의 형태를 다양한 시점에서 확보해 특정 방향 외형 과적합을 줄이기 위한 표본이다.

`컬럼정보`에 남아 있는 RT45의 로봇 시점 설명은 legacy collection label로 취급한다. **RT45를 실제 Robot camera installation angle의 ground truth로 해석하지 않는다.**

동일 `Group_ID`는 train/validation/test로 절대 분리하지 않는다.

## 4. 측정 / label 의미

- `Length`, `Width`, `Weight_g`는 실측 ground truth다.
- `JM`인데 세 실측값 일부가 NULL인 행은 의도적 미측정일 수 있다.
- 따라서 `NULL = 오류`로 자동 판정하지 않는다.
- 단, 해당 target이 필요한 regression task에는 사용할 수 없다.
- `Grade=JM`과 `Health=MAL`은 독립 개념이다.
- `JM`은 소과/기형/상품성 저하 등을 포함할 수 있고, `MAL`은 기형 health state다.

## 5. 위치

원본 source label을 보존한다.

```text
Farm = M
Zone = 숲촌1동-4-C
```

내부에서 필요할 때만 다음처럼 파싱한다.

```text
farm = M
house = 숲촌1동
bed = 4
zone = C
```

원본 Zone 문자열은 절대 버리지 않는다.

`농가_베드길이`의 농가/동/베드 수/길이/비고를 위치 context에 사용할 수 있다. 철파이프는 Zone 내부 상대 위치 anchor로만 사용하며 `파이프 N개 = 공통 몇 m` 하드코딩을 금지한다.

## 6. 영상

기존 `DataType=V`를 사용한다. 필요 시 별도 metadata에 다음을 추가한다.

- `duration`
- `observed_pipe_count`
- `start_anchor`
- `end_anchor`
- `capture_session_id`

동일 video/capture session과 동일 fruit track은 split을 넘지 않는다.

## 7. 데이터 분리

사진:
- row random split 금지
- `Group_ID` atomic split
- near-duplicate/background leakage audit

영상:
- video/capture session atomic split
- fruit track cross-split 금지

가격:
- chronological split
- target date 이후 정보 사용 금지

Field data:
- public train/valid/test와 역할 분리
- `FIELD_TEST`는 독립 평가
- tuning에 사용한 field set은 더 이상 pristine holdout이 아님

## 8. Snapshot

학습 전에 다음을 고정한다.

```yaml
snapshot_id: FIELD_PHOTO_v001
source: 딸기_프로젝트
source_tabs: [컬럼정보, 농가_딸기데이터, 농가_베드길이]
schema_version: v1
manifest_hash: ...
row_count: ...
eligible_count_by_task: {}
excluded_count_by_reason: {}
created_at: ...
```

Snapshot 이후에는 원본 Sheet 변경이 기존 실험 결과를 소급 변경하지 않는다.

## 9. Missing / Invalid

금지:
- NULL을 임의 0으로 대입
- JM 측정 NULL을 자동 오류 처리
- 위치를 추정값으로 덮어쓰기
- `Final_Name` 존재만으로 READY 판정

Task별 required/optional field를 분리하고 exclusion reason을 manifest에 남긴다.

## 10. 외부 데이터

외부 데이터는 Source Registry → Download → Audit → Normalize → Dedup → Split → Immutable Snapshot 단계를 거친다. 다운로드 성공은 학습 승인과 동일하지 않다.

## 11. 가격 시나리오 날짜

```text
source_harvest_date = Sheet 원본 provenance
scenario_date       = 가격 예측/백테스트 대상일
```

`SCENARIO_BACKTEST`에서는 date feature를 `scenario_date` 기준으로 만들고, 당일 실제 가격은 모델 입력이 아니라 사후 `ACTUAL_MARKET_REFERENCE`로만 사용한다.

## 12. 버전

- `DATA_SCHEMA_VERSION`
- `DATASET_VERSION`
- `LABEL_POLICY_VERSION`
- `MODEL_VERSION`
- `RULE_VERSION`

모든 공식 실험은 source IDs, snapshot/manifest hash, split manifest, model source IDs, Optuna study/params, 최종 metric을 함께 기록한다.
