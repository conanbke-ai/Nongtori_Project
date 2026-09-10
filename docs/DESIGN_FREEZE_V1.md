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
- farm/capture-session ingestion boundary
- raw source protection
- incremental ingestion / revision semantics
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

핵심 의미:
- `Group_ID`: 동일 딸기의 다각도 관측 묶음
- `F/RT45`: 다양한 시점 확보용. RT45는 실제 Robot camera placement 검증값이 아님
- `Length/Width/Weight_g`: ground truth
- `Maturity`: 0~4 유지
- `Grade`: SP/HI/MD/JM/NA
- `Health`: NOR/MIT/MIT_R/ANT/MAL/OTH
- `Grade in {SP,HI,MD,JM}`: 실제 수확물
- `Grade=NA`: 미수확 개체
- `Health=MAL → Grade=JM`, 역방향은 성립하지 않음
- 원본 Farm/Zone 보존
- Google Sheet 컬럼을 모델 편의상 자동 추가하지 않음

상세 label 의미는 `FIELD_DATA_CONTRACT.md`, `LABEL_MAPPING_POLICY.md`를 따른다.

## 3. Label Mapping freeze

```text
Source Native Label
→ Canonical Phenology
→ Nongtori Task Label
```

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

금지:
- `Maturity 4 → Grade JM`
- `Grade JM → OVERRIPE`
- `Grade JM → Health MAL`
- `JM → JAM`
- `FULL → JAM`
- `Maturity 3 → HARVEST`

Field Harvest ground truth:

```text
Grade in {SP,HI,MD,JM} → observed_harvest = true
Grade == NA             → observed_harvest = false
```

## 4. Incremental ingestion freeze

원본 Google Sheet/사진/영상은 read-only canonical source로 유지한다.

최초 1회 baseline 이후에는 매 실행마다 전체 source를 비교용으로 읽되, 저장/복사는 변화가 있는 항목만 수행한다.

```text
NEW        → 신규 revision 추가
UNCHANGED  → 아무 작업 없음
UPDATED    → 기존 SUPERSEDED + 새 ACTIVE revision
REMOVED    → REMOVED_FROM_SOURCE 상태 기록
INVALID    → 오류 상태 기록, 원본 보존
```

기존 revision을 덮어쓰지 않는다.

행 변경 감지:

```text
source_key + row_hash
```

Asset 변경 감지:

```text
content_sha256
```

동일 content hash는 Working Asset Store에서 재사용한다.

## 5. Multi-farm ingestion boundary

최소 관리 경계:

```text
farm_id + capture_session_id
```

다른 농가/세션을 하나의 rename/audit/change-detection job에 섞지 않는다.

## 6. Source key / revision freeze

기본 source key:

```text
farm_id + ':' + ID
```

ID 유일성이 capture session 내로 제한되면:

```text
farm_id + ':' + capture_session_id + ':' + ID
```

Revision 상태:
- `ACTIVE`
- `SUPERSEDED`
- `REMOVED_FROM_SOURCE`
- `INVALID`

UPDATED는 field-level diff를 남긴다.

## 7. Photo rename / audit freeze

기본 매칭 우선순위:

```text
1. Original_No exact
2. EXIF/capture timestamp 보조
3. natural order fallback
```

blocking audit:
- file/row count mismatch
- missing/extra file
- empty/duplicate Final_Name
- duplicate/unmatched Original_No
- unsupported extension
- target collision
- same source name + changed content hash
- invalid metadata

blocking error가 있으면 rename 단계를 중단한다.

원본 직접 rename은 기본 OFF다.

이미 validated된 동일 content hash asset은 재복사/rename하지 않는다.

## 8. Training Snapshot freeze

Training Snapshot은 매번 전체 source/assets를 복제하는 물리 사본이 아니다.

```text
latest eligible ACTIVE revisions
+ referenced asset hashes
→ normalize
→ dedup
→ split
→ immutable snapshot manifest
```

불변성은 다음 hash 집합으로 보장한다.

```text
source_revision_set_hash
asset_hashes
normalized_manifest_hash
split_manifest_hash
```

동일 asset은 여러 snapshot에서 재사용 가능하다.

## 9. UI role boundary

Farmer/Worker UI는 결과와 현장 행동 중심이다.

Operator Data Center는 다음을 관리한다.
- NEW / UPDATED / REMOVED / INVALID
- revision history / changed fields
- file ↔ metadata audit
- rename preview/manifest
- working asset reuse
- dataset/snapshot 상태

## 10. Location

원본 `Farm` + `Zone`을 보존하고 내부에서만 derive한다. 철파이프는 Zone 내부 relative anchor이며 공통 거리 하드코딩을 금지한다.

## 11. Decision Policy

- 병해충: `ALERT_AND_VERIFY`
- 숙도/등급/용도: `AUTO_DECIDE`
- 시스템/데이터/모델 오류: `SYSTEM_EXCEPTION`

## 12. Fruit pipeline

```text
Fruit Detection
→ Tracking
→ Multi-frame Ripeness
→ Harvest Decision
→ Quality / Grade
→ FRESH / PROCESSING_JAM / REJECT
```

## 13. Tracking

V1:
- 동일 연속 영상/scan session 내 identity
- ByteTrack baseline
- moving-camera 필요 시 BoT-SORT 비교

Future:
- custom persistent ReID
- session 간 global fruit ID

## 14. Split / leakage

- 동일 Group_ID cross-split 금지
- 동일 video/capture session cross-split 금지
- 동일 fruit track cross-split 금지
- 가격 random split 금지
- target date 이후 정보 사용 금지
- FIELD_TEST tuning 사용 시 pristine holdout 지위 상실

## 15. Failure

Ingestion mismatch/change conflict를 정상 처리로 덮지 않는다.

```text
blocking mismatch
→ PREFLIGHT_BLOCKED
→ source 변경 없음
→ operator notification
```

## 16. Model acceptance

임의 숫자 threshold를 사전 발명하지 않는다. baseline 대비 개선 + operational metric + independent test/field validation으로 판단한다.

## 17. External data pipeline

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

## 18. Design Review 재오픈 조건

- Maturity 0~4 자체 변경
- Grade harvest semantics 변경
- `JM/MAL/Usage` 의미축 통합
- 원본 Google Sheet/사진/영상 자동 write를 기본 동작으로 변경
- append-only revision 대신 기존 revision overwrite를 기본으로 변경
- REMOVED source를 즉시 물리 삭제하는 정책으로 변경
- farm/capture-session 경계 제거
- Training Snapshot을 source physical full copy와 동의어로 변경
- 운영자 ingestion 기능을 농민 필수 조작 흐름으로 변경
- field holdout/test를 train/tuning에 혼합
- external source provenance 제거

## 19. Implementation Gate

- [x] ARCHITECTURE 일치
- [x] DATA_STRATEGY 일치
- [x] FIELD_DATA_CONTRACT 일치
- [x] LABEL_MAPPING_POLICY 일치
- [x] DATA_INGESTION_MANAGEMENT 일치
- [x] MULTI_FARM_DATA_MODEL 일치
- [x] AI_DATA_PIPELINE_DESIGN 일치
- [x] DATA_SPLIT_POLICY 일치
- [x] FAILURE_EXCEPTION_POLICY 일치
- [x] MODEL_ACCEPTANCE_POLICY 일치

Implementation Gate: **PASS**

다음 canonical workstream:

```text
Incremental Ingestion Scanner / Change Detector / Revision Ledger
+ Field Task Audit
+ Farm-scoped Rename Manifest
+ External Annotation Audit
→ Training Snapshot v001
→ Baseline Model
→ Optuna
```
