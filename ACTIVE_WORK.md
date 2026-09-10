# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch: `main` = 1/5
- GitHub `delete_branch_on_merge=true` 적용 확인: 병합된 feature branch는 자동 삭제

| Workstream | Canonical branch / PR | 상태 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | 2026-09-08 | 기존 foundation 유지 |
| Nongtori Design Freeze v1 | `main` | DESIGN_FROZEN / DATA_WIP | 2026-09-10 | label semantics, farm/session 경계, incremental ingestion/revision semantics 유지 |
| Canonical application source 편입 | `main` / merged PR #2 | MERGED_BASELINE | 2026-09-10 | 운영센터 baseline 유지 |
| AI Data Pipeline v1 Core | `main` / merged PR #3 | MERGED_BASELINE | 2026-09-10 | Dataset Registry/provider/audit baseline 유지 |
| Normalize / Dedup / Split / Training Snapshot v1 | `main` / merged PR #4 | MERGED_BASELINE | 2026-09-10 | label normalize, exact dedup, atomic split, immutable snapshot 유지 |
| Farm-scoped Data Ingestion Design | `main` / merged PR #5 + follow-up docs | DESIGN_FROZEN | 2026-09-10 | incremental scan/change detection + append-only revision + content-hash asset reuse |
| Incremental Ingestion + Field Task Audit v1 | `main` / merged PR #6 | MERGED_BASELINE | 2026-09-10 | `NEW/UPDATED/REMOVED/UNCHANGED`, revision ledger, STR/LEF task 분리 완료 |
| Farm-scoped Rename Manifest + Working Asset Reuse v1 | `main` / merged PR #7 | MERGED_BASELINE | 2026-09-10 | Original_No exact, blocking preflight, SHA-256 object store reuse, Final_Name logical view 완료 |
| External Annotation Audit v1 | `main` / merged PR #8 | MERGED_BASELINE | 2026-09-10 | Strawberry-DS YOLO audit, KGCV LabelMe/decimal-stage audit 완료 |
| Actual Audit Evidence Gate v1 | `main` / merged PR #9 | MERGED_BASELINE | 2026-09-10 | Strawberry-DS canonical expectation, derivative mismatch 감지, KGCV evidence gate 완료 |
| Shared Source Asset Relation v1 | `main` / merged PR #10 | MERGED_BASELINE | 2026-09-10 | 하나의 physical asset을 여러 sample row가 공유할 수 있도록 many-to-one relation, distinct asset count preflight, context conflict blocking, shared object-store reuse 반영 완료 |

## 다음 canonical workstream

```text
실제 raw annotation 확보/실행
→ AgML turning-red empirical calibration
→ Field source asset 연결
→ Actual Field + External Normalized Manifest
→ Actual Dedup / Split
→ Training Snapshot v001
→ Baseline Model
→ Optuna
```

### 현재 구현 완료 핵심

- 원본 Google Sheet/사진/영상 read-only
- incremental ingestion + revision ledger
- STR/LEF task eligibility 분리
- farm/capture-session rename preflight + content-addressed working asset reuse
- `SampleRow → SourceAsset` many-to-one 허용
- 같은 `Original_No`의 sample row가 동일 Date/Zone/DataType이면 `SHARED_SOURCE_ASSET`로 처리
- 동일 `Original_No`가 Date/Zone/DataType에서 충돌하면 `SOURCE_ASSET_CONTEXT_CONFLICT`로 blocking
- source file count는 Sheet row 수가 아니라 distinct valid Original_No 수와 비교
- Strawberry-DS 6-class YOLO annotation audit parser
- KGCV 7 main stage + diameter/length/decimal_stage annotation audit parser
- `turning red` Maturity 2/3 threshold는 관측 분포와 field calibration 전까지 `DO_NOT_INVENT_THRESHOLD`
- Strawberry-DS canonical expectation: 247 image/label pairs, 1,062 boxes; derivative count mismatch 자동 감지
- DATA-RIP-002 expectation: 1,477 rows / 3,997 boxes; per-class/decimal-stage 분포는 raw audit 전 미확정
- actual audit report와 expectation을 비교하는 MATCH/MISMATCH gate 구현
- CI는 `tests/test_*.py` 전체 discovery

### 2026-09-10 실제 source audit findings

- live Sheet `농가_딸기데이터`에서 ID가 있는 active metadata row 110개 확인
- STR 98 / LEF 12
- 같은 `Original_No`가 여러 sample row에 사용되는 shared-source 사례 확인
- 같은 `Original_No`가 서로 다른 Zone에 재사용된 context-conflict 사례 확인
- M/C/U 촬영 폴더를 Drive에서 직접 열람했으나 현재 모두 비어 있음
- 따라서 field image SHA-256과 실제 materialized Working Asset은 아직 생성할 수 없음

### 현재 외부 입력 blocker

1. DATA-RIP-002 full raw annotation archive가 현재 실행 환경에 없음
2. Zenodo KGCV 원본 ZIP은 대용량(약 2.4GB / 4.3GB)이라 현재 세션에서 metadata-only 추출이 불가
3. Drive의 농가별 촬영 폴더가 현재 비어 있어 actual field image asset이 없음
4. 따라서 KGCV per-class/turning-red 실제 분포와 field image SHA-256을 포함한 Training Snapshot v001은 아직 생성 불가

### 다음 실행 핵심

1. KGCV raw tagged/random annotation 확보 후 `audit-kgcv` + expectation gate
2. class/decimal-stage distribution 검토 후 turning-red empirical calibration
3. field 사진이 `촬영/<농가>` 폴더에 연결되면 shared-source-aware rename-preflight/materialize-working-assets 실행
4. Field + External actual normalized manifest 생성
5. actual dedup/split manifest 및 Training Snapshot v001 생성

새 AI/data 구현은 `docs/DESIGN_FREEZE_V1.md`, `docs/LABEL_MAPPING_POLICY.md`, `docs/DATA_INGESTION_MANAGEMENT.md`, `docs/SOURCE_ASSET_SAMPLE_RELATION.md`, `docs/MULTI_FARM_DATA_MODEL.md`, `docs/EXTERNAL_DATA_AUDIT_EVIDENCE.md`를 기준으로 한다.

## Branch hygiene

- feature branch는 실제 독립 구현 workstream에만 생성
- PR merge 후 GitHub 자동 삭제
- 기준 상태 보존은 backup branch보다 tag 우선

## 데이터 안전

Google Sheets/외부 원본/현장 사진·영상은 read-only source다. 기존 revision과 asset은 덮어쓰지 않는다. 학습/평가는 latest eligible ACTIVE revision을 선택해 immutable Training Snapshot manifest로 고정한다.
