# Nongtori AI Data Pipeline Design

Status: **IMPLEMENTED_V1_CORE / INCREMENTAL_INGESTION_NEXT**

## 1. 목표

외부 표본 데이터와 Nongtori field data를 재현 가능한 방식으로 수집·감사·정규화·분리·snapshot한다. 모델마다 임시 다운로드/수작업 라벨 변환을 반복하지 않는다.

현장 원본은 직접 수정하지 않는다. Google Sheet·원본 사진/영상은 read-only canonical source로 보존하고, 최초 baseline 이후에는 source scan + change detection + revision ledger 기반 증분 ingestion을 사용한다.

## 2. 전체 파이프라인

```text
External Dataset Providers
→ DatasetRegistry
→ DatasetDownloader / Provider Adapter
→ Raw
→ Safe Extract
→ Source / License Audit
→ Integrity / Label Audit
→ Normalize
→ Deduplicate
→ Split
→ Immutable Snapshot
→ Baseline Model
→ Optuna
→ Evaluation
```

Field data:

```text
Google Sheet / Raw Photo / Raw Video (READ ONLY)
→ Initial Baseline Scan (1회)
→ 이후 Source Scan / Change Detection
→ NEW / UPDATED / REMOVED / UNCHANGED
→ Revision Ledger / Working Asset Store
→ farm_id + capture_session_id boundary
→ File ↔ Metadata Preflight Audit
→ Rename Manifest / Validated Working Assets
→ FieldSpreadsheetAdapter / Asset Adapter
→ Schema / Semantic / Task Audit
→ Normalize
→ Dedup
→ Split
→ Immutable Training Snapshot Manifest
```

상세 ingestion 규칙은 `DATA_INGESTION_MANAGEMENT.md`를 canonical 기준으로 사용한다.

## 3. 현재 구현 상태

`ml/data_pipeline/`에 V1 core + Normalize/Dedup/Split/Training Snapshot이 구현되어 있다.

구현 완료:
- JSON source record 기반 `DatasetRegistry`
- Provider Adapter: Mendeley / Hugging Face / Direct HTTP / Kaggle / AI-Hub
- version/revision 고정 source record
- streaming download + SHA-256 checksum
- 안전한 ZIP/TAR extraction(path traversal 차단)
- file manifest(`manifest.csv`)
- empty file / exact duplicate checksum audit
- field/external label normalization
- canonical label mapping config
- exact SHA-256 dedup
- atomic group split + leakage guard
- immutable training snapshot metadata/hash
- CLI 및 unit test/CI

다음 구현/검증 Gate:
- incremental source scanner / change detector
- source revision ledger / asset revision store
- field task audit에서 STR/LEF 등 대상별 eligibility 분리
- farm/capture session 기반 ingestion audit
- Original_No/Final_Name 기반 photo rename manifest
- DATA-RIP-001/002 actual annotation/class audit
- AgML decimal stage 기반 `turning red` calibration
- 실제 field/external normalized manifest 및 Training Snapshot v001

## 4. Incremental Field Source Lifecycle

```text
BASELINE
→ SCANNED
→ NEW | UPDATED | REMOVED | UNCHANGED | INVALID
→ REVISION_RECORDED
→ PREFLIGHT_BLOCKED | PREFLIGHT_PASSED
→ WORKING_ASSET_READY
→ NORMALIZED
→ SNAPSHOT_READY
```

행 변경 판정:

```text
NEW        source_key 없음
UNCHANGED  source_key 있음 + row_hash 동일
UPDATED    source_key 있음 + row_hash 변경
REMOVED    이전에는 존재했으나 현재 source에서 사라짐
INVALID    schema/semantic contract 위반
```

`UPDATED`는 기존 revision을 덮어쓰지 않는다. 기존 revision은 `SUPERSEDED`, 새 revision은 `ACTIVE`로 append한다.

`REMOVED`도 물리 삭제하지 않고 `REMOVED_FROM_SOURCE`로 보존한다.

## 5. Source Key / Hash

Field source key는 기본적으로 다음을 사용한다.

```text
farm_id + ID
```

source 특성상 ID가 capture session 내에서만 유일한 경우:

```text
farm_id + capture_session_id + ID
```

행 비교는 canonical source fields의 SHA-256 `row_hash`를 사용하고, UPDATED에서는 changed_fields diff를 함께 저장한다.

Asset은 `content_sha256`으로 식별하고 동일 hash는 working store에서 재사용한다.

같은 filename/Original_No인데 hash가 변경되면 자동 덮어쓰기하지 않고 `SAME_SOURCE_NAME_CONTENT_CHANGED`로 audit한다.

## 6. Raw / Git 정책

raw 외부 데이터와 private field 원본은 Git에 넣지 않는다.

Git에 저장 가능:
- source JSON
- source scan/checkpoint ID/checksum
- README/source notes
- aggregate manifest/checksum
- label mapping/split manifest
- aggregate audit result
- config/script

Git에 저장하지 않음:
- raw image/video/archive
- private field row-level source snapshot
- revision ledger의 private row payload
- 재배포 제한 원본
- 대용량 model weights

## 7. Field ingestion gate

모든 현장 ingestion은 `farm_id + capture_session_id`를 경계로 한다.

Preflight에서 최소 검증:
- Sheet 대상 row 수
- 실제 asset 수
- Original_No exact match
- Final_Name 존재/중복
- missing/extra/unmatched asset
- target filename collision
- 지원 확장자
- source scan provenance

blocking mismatch가 있으면 rename/normalize를 진행하지 않는다.

기존에 동일 content hash가 validated working asset으로 존재하면 새로 복사하지 않고 기존 asset을 참조한다.

## 8. Audit gate

Core audit:
- file count/size
- SHA-256
- empty file
- exact duplicate hash
- extension distribution

승격 전 추가 audit:
- image/video decode
- annotation format
- class distribution
- field Class/DataType별 task eligibility
- near duplicate
- label ambiguity
- license/commercial/redistribution constraint
- revision consistency / source-key collision

## 9. Normalize

원본 label은 보존하고 normalized field를 별도 생성한다.

```text
original_label
→ mapping version
→ canonical stage / task label
```

Google Sheet는 수정하지 않는다. 파생값은 normalized manifest에서만 만든다.

Field fruit label semantics:
- `Grade=SP/HI/MD/JM` → observed harvest true
- `Grade=NA` → observed harvest false
- `Health=MAL` → field contract상 `Grade=JM`
- `Maturity=3`은 harvest 여부와 분리

STR가 아닌 LEF 등 대상은 fruit ripeness task에 억지로 통과시키지 않고 task별 eligibility에서 분리한다.

DATA-RIP-001/002는 source annotation 정의를 보존한다. AgML/KGCV의 `turning red`는 decimal stage calibration 전까지 자동 2/3 mapping을 강제하지 않는다.

## 10. Dedup / Split

split 전에 dedup한다.

Field image:
- latest eligible ACTIVE revision만 대상
- Group_ID atomicity
- capture_session provenance 유지

Video:
- video/capture session atomicity
- fruit track cross-split 금지

External:
- sequence/folder/source semantics를 audit해 atomic group을 정의

Price:
- chronological split

## 11. Training Snapshot

Training Snapshot은 매 버전마다 전체 source/asset을 물리 복제하지 않는다.

```text
Revision Ledger / Working Asset Store
→ latest eligible ACTIVE revision selection
→ normalized manifest
→ dedup / split
→ immutable Training Snapshot manifest
```

Snapshot에는 최소 다음을 고정한다.

```yaml
snapshot_id: ...
source_scan_ids: []
source_revision_set_hash: ...
asset_hashes: []
schema_version: ...
label_mapping_version: ...
normalized_manifest_hash: ...
split_manifest_hash: ...
created_at: ...
```

동일 content hash asset은 여러 snapshot에서 재사용할 수 있다. Snapshot 불변성은 참조한 revision/hash 집합으로 보장한다.

## 12. Experiment linkage

모든 baseline/Optuna/final run은 다음을 기록한다.

- source scan/checkpoint ID/hash
- source revision set hash
- training snapshot ID/hash
- split manifest
- model source ID
- config hash
- seed
- Optuna study/trial/best params
- environment/package versions
- metric artifact
- checkpoint hash

## 13. 운영 UI 경계

Farmer/Worker UI:
- 수집 건수
- 분석 완료/대기/오류
- 현장 행동/알림

Operator Data Center:
- 농가별/capture session별 NEW/UPDATED/REMOVED/INVALID
- raw/working asset 상태
- file ↔ metadata audit
- revision history / changed fields
- rename preview/manifest
- source/training snapshot 상태

내부 데이터 엔지니어링 정보를 농민 화면에 그대로 노출하지 않는다.

## 14. 구현 우선순위

```text
현재
Incremental Ingestion Scanner / Revision Ledger
+ Field Task Audit
+ Farm-scoped Rename Manifest
+ DATA-RIP-001/002 Annotation Audit

그 다음
Actual Normalized Manifest
→ Actual Dedup/Split
→ Training Snapshot v001

그 다음
Baseline Model → Optuna → Evaluation
```
