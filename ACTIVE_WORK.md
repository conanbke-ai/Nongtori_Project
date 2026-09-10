# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch: `main` = 1/5
- GitHub `delete_branch_on_merge=true` 적용 확인: 병합된 feature branch는 자동 삭제

| Workstream | Canonical branch / PR | 상태 | Owner / Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | owner 없음 | 2026-09-08 | 기존 foundation 유지 |
| Nongtori Design Freeze v1 | `main` | DESIGN_FROZEN / DATA_WIP | owner 없음 / canonical docs | 2026-09-10 | label semantics, farm/session 경계, incremental ingestion/revision semantics 유지 |
| Canonical application source 편입 | `main` / merged PR #2 | MERGED_BASELINE | owner 없음 | 2026-09-10 | 운영센터 baseline 유지 |
| AI Data Pipeline v1 Core | `main` / merged PR #3 | MERGED_BASELINE | owner 없음 | 2026-09-10 | Dataset Registry/provider/audit baseline 유지 |
| Normalize / Dedup / Split / Training Snapshot v1 | `main` / merged PR #4 | MERGED_BASELINE | owner 없음 | 2026-09-10 | label normalize, exact dedup, atomic split, immutable snapshot 유지 |
| Farm-scoped Data Ingestion Design | `main` / merged PR #5 + follow-up docs | DESIGN_FROZEN | owner 없음 | 2026-09-10 | baseline 1회 + incremental scan/change detection + append-only revision + content-hash asset reuse |
| Incremental Ingestion + Field Task Audit v1 | `main` / merged PR #6 | MERGED_BASELINE | owner 없음 | 2026-09-10 | `NEW/UPDATED/REMOVED/UNCHANGED`, revision ledger, field-level diff, STR/LEF task 분리, blank template row skip, CLI/CI 완료 |

## 다음 canonical workstream

```text
Farm-scoped Rename Manifest + Working Asset Reuse
+ DATA-RIP-001 / DATA-RIP-002 Annotation Audit
→ Actual Normalized Manifest
→ Actual Dedup / Split
→ Training Snapshot v001
→ Baseline Model
→ Optuna
```

### 현재 구현 완료 핵심

- Google Sheet/원본 사진·영상은 read-only canonical source
- 최초 1회 baseline 이후 전체 재복사 금지
- 이후 source는 전체를 비교하되 `NEW/UPDATED/REMOVED/UNCHANGED` 판정
- unchanged는 새 revision 생성 안 함
- updated는 새 revision append + changed fields diff
- removed는 물리 삭제 없이 `REMOVED_FROM_SOURCE`
- Field ripeness task는 `STR`만 eligible
- `LEF`는 `NON_FRUIT_RIPENESS_TARGET`로 명시 제외
- ID 없는 template/빈 행은 ingestion/normalize 대상에서 제외
- 최소 데이터 경계는 `farm_id + capture_session_id`
- Training Snapshot은 physical full copy가 아니라 revision/hash 집합 manifest

### 다음 구현 핵심

1. `Original_No` exact 기반 photo matching
2. EXIF 보조 / natural-order fallback
3. blocking mismatch 시 rename 중단
4. content SHA-256 기준 Working Asset 재사용
5. rename manifest + rollback metadata
6. 외부 DATA-RIP-001/002 실제 annotation audit
7. AgML `turning red` decimal-stage calibration

새 AI/data 구현은 `docs/DESIGN_FREEZE_V1.md`, `docs/LABEL_MAPPING_POLICY.md`, `docs/DATA_INGESTION_MANAGEMENT.md`, `docs/MULTI_FARM_DATA_MODEL.md`를 기준으로 한다.

## 작업 시작 체크

1. `main` 실제 구현 확인
2. Design Freeze 확인
3. ACTIVE_WORK 확인
4. open PR 확인
5. remote branch budget 확인
6. docs/설계와 기존 asset 확인
7. active lease 확인
8. `ALREADY_DONE / IN_PROGRESS / NEW / BLOCKED` 판정
9. NEW일 때만 branch/lease 확보

## Branch hygiene

- 같은 목적의 `v2/v3/final/actual/real` branch 생성 금지
- feature branch는 실제 독립 구현 workstream에만 생성
- PR merge 후 GitHub 자동 삭제를 기본값으로 사용
- 기준 상태 보존은 backup branch보다 tag 우선

## 데이터 안전

Google Sheets/외부 원본/현장 사진·영상은 read-only source다. 기존 revision과 asset은 덮어쓰지 않는다. 학습/평가는 latest eligible ACTIVE revision을 선택해 immutable Training Snapshot manifest로 고정한다.
