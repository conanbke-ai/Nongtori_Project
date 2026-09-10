# Nongtori AI Data Pipeline Design

Status: **IMPLEMENTED_V1_CORE / INGESTION_AND_ANNOTATION_AUDIT_NEXT**

## 1. 목표

외부 표본 데이터와 Nongtori field data를 재현 가능한 방식으로 수집·감사·정규화·분리·snapshot한다. 모델마다 임시 다운로드/수작업 라벨 변환을 반복하지 않는다.

현장 원본은 직접 수정하지 않는다. Google Sheet·원본 사진/영상은 read-only canonical source로 보존하고, export snapshot/Working Copy를 통해 파이프라인에 진입시킨다.

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
→ Source Export / Working Copy
→ farm_id + capture_session_id boundary
→ File ↔ Metadata Preflight Audit
→ Rename Manifest / Validated Working Assets
→ FieldSpreadsheetAdapter / Asset Adapter
→ Schema / Semantic / Task Audit
→ Normalize
→ Dedup
→ Split
→ Immutable Training Snapshot
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
- field task audit에서 STR/LEF 등 대상별 eligibility 분리
- farm/capture session 기반 ingestion audit
- Original_No/Final_Name 기반 photo rename manifest
- Working Copy rename/rollback
- DATA-RIP-001/002 actual annotation/class audit
- AgML decimal stage 기반 `turning red` calibration
- 실제 field/external normalized manifest 및 Training Snapshot v001

## 4. Source lifecycle

- `DISCOVERED`
- `REVIEW_REQUIRED`
- `AUTH_REQUIRED`
- `DOWNLOADED`
- `AUDITED`
- `APPROVED`
- `NORMALIZED`
- `SNAPSHOT_READY`
- `IN_USE`
- `REJECTED`
- `RETIRED`
- `SUPERSEDED`

`DOWNLOADED != APPROVED`.

Field source는 추가로 ingestion 상태를 가진다.

```text
SOURCE_DISCOVERED
→ SOURCE_EXPORTED
→ PREFLIGHT_BLOCKED | PREFLIGHT_PASSED
→ WORKING_COPY_READY
→ RENAMED_VALIDATED
→ NORMALIZED
→ SNAPSHOT_READY
```

## 5. Downloader interface

```text
DatasetRegistry
  → source record
DatasetDownloader
  → provider adapter
ProviderAdapter
  → version-pinned download
```

Provider별 동작:
- Mendeley: public dataset file API
- Hugging Face: `snapshot_download` + pinned revision
- Direct HTTP: streamed download
- Kaggle: authenticated CLI
- AI-Hub: official `aihubshell` + approval/API key

## 6. Raw / Git 정책

raw 외부 데이터와 private field 원본은 Git에 넣지 않는다.

Git에 저장 가능:
- source JSON
- source snapshot ID/checksum
- README/source notes
- aggregate manifest/checksum
- label mapping/split manifest
- aggregate audit result
- config/script

Git에 저장하지 않음:
- raw image/video/archive
- private field row-level source snapshot
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
- source snapshot provenance

blocking mismatch가 있으면 rename/normalize를 진행하지 않는다.

기본 rename 대상은 원본이 아니라 Working Copy다.

```text
Raw Source Folder
→ Working Copy
→ temporary safe rename
→ Final_Name
→ post-rename integrity audit
```

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
- Group_ID atomicity
- capture_session provenance 유지

Video:
- video/capture session atomicity
- fruit track cross-split 금지

External:
- sequence/folder/source semantics를 audit해 atomic group을 정의

Price:
- chronological split

## 11. Snapshot

Source snapshot과 training snapshot을 구분한다.

```text
Source Snapshot
= 원본 Google Sheet/export/raw asset의 특정 시점 복사본 provenance

Training Snapshot
= ingestion audit + normalize + dedup + split을 통과한 학습 입력
```

Snapshot ID overwrite는 금지한다.

```yaml
snapshot_id: ...
source_snapshot_ids: []
source_ids: []
source_versions: []
schema_version: ...
label_mapping_version: ...
manifest_hash: ...
split_manifest_hash: ...
created_at: ...
```

## 12. Experiment linkage

모든 baseline/Optuna/final run은 다음을 기록한다.

- source snapshot ID/hash
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
- 농가별/capture session별 raw/working asset 상태
- file ↔ metadata audit
- rename preview/manifest
- 누락/초과/중복/충돌
- source/training snapshot 상태

내부 데이터 엔지니어링 정보를 농민 화면에 그대로 노출하지 않는다.

## 14. 구현 우선순위

```text
현재
Field Task Audit + Farm-scoped Ingestion/Rename Manifest
+ DATA-RIP-001/002 Annotation Audit

그 다음
Actual Normalized Manifest
→ Actual Dedup/Split
→ Training Snapshot v001

그 다음
Baseline Model → Optuna → Evaluation
```
