# Nongtori AI Data Pipeline Design

Status: **READY_FOR_IMPLEMENTATION_AFTER_DESIGN_FREEZE**

## 1. 목표

외부 표본 데이터와 Nongtori field data를 재현 가능한 방식으로 수집·감사·정규화·분리·snapshot한다. 모델마다 임시 다운로드/수작업 라벨 변환을 반복하지 않는다.

## 2. 전체 파이프라인

```text
DatasetRegistry
→ DatasetDownloader
→ Provider Adapter
   ├─ HuggingFace
   ├─ Mendeley
   ├─ Direct HTTP
   ├─ Kaggle
   └─ AIHub
→ Raw
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
Google Sheet (WORKING SOURCE)
→ FieldSpreadsheetAdapter
→ Schema / semantic audit
→ Task eligibility
→ Dedup
→ Split
→ Immutable Snapshot
```

## 3. Source lifecycle

- `DISCOVERED`
- `DOWNLOADED`
- `AUDITED`
- `APPROVED`
- `NORMALIZED`
- `SNAPSHOT_READY`
- `REJECTED`

Registry에서는 `RETIRED`, `SUPERSEDED`, `AUTH_REQUIRED`도 영구 기록한다.

## 4. Downloader interface

```text
DatasetRegistry
  → source record
DatasetDownloader
  → provider adapter
ProviderAdapter
  → discover/version/download/verify
```

Downloader는 provider-specific 인증/URL/파일구조를 숨기고 pipeline은 표준 manifest만 본다.

## 5. Raw / Git 정책

raw 외부 데이터와 private field 원본은 Git에 넣지 않는다.

Git에 저장:
- `SOURCE.json` 또는 source YAML
- `README_SOURCE.md`
- `manifest.csv`
- checksum
- label mapping
- split manifest
- audit result
- config/script

## 6. Audit gate

다운로드 후 최소 확인:

- source/version/license
- 파일 integrity/checksum
- 이미지/영상 decode 가능 여부
- annotation 존재/형식
- class distribution
- duplicate/near-duplicate
- corrupt/empty file
- label mapping ambiguity
- commercial/redistribution constraint

`DOWNLOADED != APPROVED`.

## 7. Normalize

원본 label은 보존하고 normalized field를 별도 생성한다.

```text
original_label
→ mapping version
→ nongtori_label
```

mapping은 source/version과 함께 관리한다.

## 8. Dedup / Split

split 전에 dedup한다.

Field image:
- Group_ID atomicity

Video:
- video/capture session atomicity
- fruit track cross-split 금지

External:
- sequence/folder/source semantics를 audit해 atomic group을 정의

Price:
- chronological split

## 9. Snapshot

Snapshot은 immutable이다.

```yaml
snapshot_id: ...
source_ids: []
source_versions: []
schema_version: ...
label_mapping_version: ...
manifest_hash: ...
split_manifest_hash: ...
created_at: ...
```

같은 snapshot ID의 내용 변경을 금지한다.

## 10. Experiment linkage

모든 baseline/Optuna/final run은 다음을 기록한다.

- snapshot ID/hash
- split manifest
- model source ID
- config hash
- seed
- Optuna study/trial/best params
- environment/package versions
- metric artifact
- checkpoint hash

## 11. 구현 우선순위

Design Freeze 이후:

```text
Dataset Registry
→ Provider Adapter / Downloader
→ Audit
→ Normalize
→ Snapshot
→ Baseline
→ Optuna
```

UI/API 확장보다 재현 가능한 데이터 pipeline을 먼저 만든다.
