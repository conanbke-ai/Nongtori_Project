# Nongtori DESIGN FREEZE v1

Status: **DESIGN_FROZEN / DATA_WIP**

이 문서는 V1 구현 전에 구조적 결정을 잠그기 위한 canonical freeze 문서다. 2026-09-10 기준 `main` 반영 및 재조회 검증을 완료했다. 이후 신규 AI/data pipeline 구현은 이 문서와 연결 정책을 기준으로 진행한다.

## 1. Freeze 원칙

```text
DESIGN FREEZE != DATA FREEZE
```

Freeze 대상:
- architecture / dependency direction
- field label semantics
- automation/decision policy
- provenance/source lifecycle
- split/leakage
- failure/exception
- model acceptance
- market backtest semantics

계속 변경 가능:
- Google Sheet 행
- 추가 사진/영상
- sample count
- 외부 dataset 승인/거절
- 최종 immutable snapshot
- model hyperparameter/threshold

## 2. Field source

`딸기_프로젝트` Google Sheet를 working canonical source로 사용한다.

Tabs:
- `컬럼정보`
- `농가_딸기데이터`
- `농가_베드길이`

핵심 의미:
- `Group_ID`: 동일 딸기의 다각도 관측 묶음
- `F/RT45`: 다양한 시점 확보용. RT45는 실제 Robot camera placement 검증값이 아님
- `Length/Width/Weight_g`: ground truth
- `Maturity`: 0~4 유지
- `Grade`: SP/HI/MD/JM/NA
- `Health`: NOR/MIT/MIT_R/ANT/MAL/OTH
- `Grade in {SP,HI,MD,JM}`: 실제 수확물
- `Grade=NA`: 미수확 개체, unknown이 아님
- `JM != MAL`
- 현장 정책상 `Health=MAL → Grade=JM`, 역방향은 성립하지 않음
- JM의 일부 측정 NULL은 의도적 미측정 가능
- 원본 Farm/Zone 보존
- 영상은 `DataType=V`
- Label Mapping 편의를 위해 원본 Google Sheet 컬럼을 추가하지 않고 파생 필드는 Normalize/Manifest에서 생성

상세 label 의미와 외부 source mapping은 `FIELD_DATA_CONTRACT.md`, `LABEL_MAPPING_POLICY.md`를 따른다.

## 3. Label Mapping freeze

원본 라벨을 보존하고 다음 3계층으로 정규화한다.

```text
Source Native Label
→ Canonical Phenology
→ Nongtori Task Label
```

Canonical phenology 기본값:

```text
GREEN_SMALL   → Maturity 0
GREEN         → Maturity 0
WHITE         → Maturity 1
TURNING_EARLY → Maturity 2
TURNING_MID   → Maturity 2
TURNING_LATE  → Maturity 3
RED_RIPE      → Maturity 4
OVERRIPE      → Maturity 4 + Grade JM
FLOWER        → ripeness task 제외
```

중요한 비대칭 규칙:

```text
OVERRIPE → Maturity 4 + Grade JM
Maturity 4 → Grade JM       # 금지
Grade JM → OVERRIPE         # 금지
Health MAL → Grade JM
Grade JM → Health MAL       # 금지
```

Field Harvest ground truth:

```text
Grade in {SP,HI,MD,JM} → observed_harvest = true
Grade == NA             → observed_harvest = false
```

`Maturity=3`에서도 실제 수확/미수확이 모두 존재할 수 있으므로 `Maturity 3 → HARVEST` 규칙을 만들지 않는다.

Harvest Decision 학습에서 Grade는 target 생성 근거로만 사용하며 input feature로 사용하지 않는다.

`JM`은 `PROCESSING_JAM`과 동의어가 아니다. `JM→JAM`, `FULL→JAM` 자동 매핑을 금지한다.

## 4. Location

원본 `Farm` + `Zone`을 보존하고 내부에서만 `farm/house/bed/zone`을 derive한다. 철파이프는 Zone 내부 relative anchor이며 공통 거리 하드코딩을 금지한다.

## 5. Decision Policy

- 병해충: `ALERT_AND_VERIFY`
- 숙도/등급/용도: `AUTO_DECIDE`
- 시스템/데이터/모델 오류: `SYSTEM_EXCEPTION`

숙도/등급은 사람이 과실마다 재검수하는 흐름으로 만들지 않는다.

## 6. Fruit pipeline

```text
Fruit Detection
→ Tracking
→ Multi-frame Ripeness
→ Harvest Decision
→ Quality / Grade
→ FRESH / PROCESSING_JAM / REJECT
```

`FULL = JAM` 같은 단순 mapping 금지.

## 7. Tracking

V1:
- 동일 연속 영상/scan session 내 identity
- ByteTrack baseline
- moving-camera 필요 시 BoT-SORT 비교

Future:
- custom persistent ReID
- session 간 global fruit ID

## 8. Split / leakage

- 동일 Group_ID cross-split 금지
- 동일 video/capture session cross-split 금지
- 동일 fruit track cross-split 금지
- 가격 random split 금지
- target date 이후 정보 사용 금지
- FIELD_TEST tuning 사용 시 pristine holdout 지위 상실

## 9. Failure

숙도/등급 low confidence는 추가 frame → temporal aggregation → system exception 순서다. 병해충 risk/ambiguous는 `VERIFY_ZONE`. 가격/외부 source failure는 명시 상태 코드로 반환한다.

## 10. Model acceptance

임의 숫자 threshold를 사전 발명하지 않는다. baseline 대비 개선 + operational metric + independent test/field validation으로 판단한다.

상태:
`REFERENCE / REPRODUCED / CANDIDATE / VALIDATED / FIELD_VALIDATED / REJECTED`.

## 11. Market price / settlement

- 범용 item/variety 구조
- 첫 검증 설향
- 예상 낙찰단가 KRW/kg
- 예상 정산 거래액
- 실제 실정산액 표현 금지

```text
source_harvest_date = 원본 provenance
scenario_date       = 테스트/예측 대상일
```

`SCENARIO_BACKTEST`는 scenario_date 이전 사용 가능 정보만 input으로 사용하고 실제 target price는 사후 reference로 분리한다.

## 12. External data pipeline

```text
Dataset Registry
→ Downloader / Provider Adapter
→ Source/License Audit
→ Integrity/Label Audit
→ Normalize
→ Dedup
→ Split
→ Immutable Snapshot
→ Baseline
→ Optuna
→ Evaluation
```

raw external/private field data는 Git에 넣지 않는다.

## 13. V1 제외

- 미래 수확량 AI forecast
- 실제 Robot navigation/SLAM
- Robot arm/gripper/conveyor control
- session 간 persistent global fruit ID
- RGB만으로 경도/당도/내부손상 확정
- 모든 병해충 완전자동지원
- 근거 없는 개인화 실수령액 주장

## 14. Freeze 후 실험 조정 가능

- ByteTrack vs BoT-SORT 최종 선택
- FPS/stride/confidence threshold
- Optuna search range
- XGBoost/CatBoost/TFT 등 최종 모델 선택
- 외부 dataset 승인/거절
- 지원 병해충 capability
- UI 카드/그래프 세부 표현
- 검증된 source별 label mapping 세부값 및 mapping confidence

## 15. Design Review 재오픈 조건

- Maturity 0~4 자체 변경
- Grade의 field harvest semantics(`NA=미수확`, 나머지 Grade=수확)를 변경
- `JM/MAL/Usage`의 의미축을 합침
- 숙도/등급을 정상 사람확인 필수 흐름으로 변경
- 병해충을 검증 없이 완전자동 방제 결정으로 변경
- persistent fruit ID를 V1 필수로 승격
- 미래 수확량 prediction을 V1 핵심으로 재도입
- 예상 거래액을 근거 없이 실수령액으로 의미 변경
- field holdout/test를 train/tuning에 혼합
- 외부 source provenance 제거

## 16. Implementation Gate

- [x] PROJECT_SCOPE 일치
- [x] ARCHITECTURE 일치
- [x] DATA_STRATEGY 일치
- [x] FIELD_DATA_CONTRACT 일치
- [x] LABEL_MAPPING_POLICY 일치
- [x] AI_DECISION_POLICY 일치
- [x] DATA_SPLIT_POLICY 일치
- [x] FAILURE_EXCEPTION_POLICY 일치
- [x] MODEL_ACCEPTANCE_POLICY 일치
- [x] MARKET_PRICE_SETTLEMENT_POLICY 일치
- [x] AI_DATA_MODEL_SOURCES registry 준비
- [x] AI_DATA_PIPELINE_DESIGN 일치
- [x] ACTIVE_WORK / open PR / branch budget 확인

Implementation Gate: **PASS**

다음 canonical workstream은 `Normalize → Dedup → Split → Training Snapshot → Baseline Model → Optuna` 순서다.
