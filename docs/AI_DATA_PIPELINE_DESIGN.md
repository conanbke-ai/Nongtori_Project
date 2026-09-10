# Nongtori AI Data Pipeline Design

Status: **IMPLEMENTED_V1_CORE / NORMALIZATION_PENDING**

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
Google Sheet (WORKING SOURCE)
→ FieldSpreadsheetAdapter
→ Schema / semantic audit
→ Task eligibility
→ Dedup
→ Split
→ Immutable Snapshot
```

## 3. 현재 구현 상태

`ml/data_pipeline/`에 V1 core가 구현되어 있다.

구현 완료:
- JSON source record 기반 `DatasetRegistry`
- Provider Adapter: Mendeley / Hugging Face / Direct HTTP / Kaggle / AI-Hub
- version/revision 고정 source record
- streaming download + SHA-256 checksum
- 안전한 ZIP/TAR extraction(path traversal 차단)
- file manifest(`manifest.csv`)
- empty file / exact duplicate checksum audit
- immutable snapshot metadata 생성 및 같은 snapshot ID overwrite 차단
- CLI: `list`, `download`, `extract`, `audit`, `snapshot`
- raw/audit/snapshot Git ignore
- core unit test 및 PR CI

다음 구현 Gate:
- source별 annotation/class audit
- Nongtori label mapping version
- Normalize
- Dedup semantic policy
- Split manifest
- `APPROVED / NORMALIZED / SNAPSHOT_READY` 승격

따라서 현재 snapshot 기능은 **audit provenance snapshot**을 만들 수 있지만, source를 학습용 `SNAPSHOT_READY`로 자동 승격하지 않는다.

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

Git에 저장:
- source JSON
- README/source notes
- manifest/checksum
- label mapping/split manifest
- audit result
- config/script

Git에 저장하지 않음:
- raw image/video/archive
- private field data
- 재배포 제한 원본
- 대용량 model weights

## 7. Audit gate

V1 core audit:
- file count/size
- SHA-256
- empty file
- exact duplicate hash
- extension distribution

승격 전 추가 audit:
- image/video decode
- annotation format
- class distribution
- near duplicate
- label ambiguity
- license/commercial/redistribution constraint

## 8. Normalize

원본 label은 보존하고 normalized field를 별도 생성한다.

```text
original_label
→ mapping version
→ nongtori_label
```

DATA-RIP-001의 6단계와 DATA-RIP-002의 7 category를 Nongtori Maturity 0~4에 임의로 합치지 않는다. 실제 annotation audit 후 mapping version을 별도 확정한다.

## 9. Dedup / Split

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

## 10. Snapshot

Snapshot ID overwrite는 금지한다.

```yaml
snapshot_id: ...
source_ids: []
source_versions: []
schema_version: ...
label_mapping_version: ...
manifest_hash: ...
created_at: ...
```

최종 학습 snapshot에는 Normalize/Dedup/Split 완료 후 split manifest hash를 추가한다.

## 11. Experiment linkage

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

## 12. 구현 우선순위

```text
V1 Core (현재)
Dataset Registry → Download → Extract → Audit → provenance snapshot

다음
Annotation Audit → Normalize → Dedup → Split → training Snapshot

그 다음
Baseline Model → Optuna → Evaluation
```
