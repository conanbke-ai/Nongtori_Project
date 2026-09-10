# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch 확인 기준: `main`, `feat/ai-data-pipeline-v1`, `feat/data-normalize-split-v1`, `feat/annotation-audit-v1` = 4/5
- `feat/ai-data-pipeline-v1`은 merged PR #3 이후 `CLEANUP_CANDIDATE`
- `feat/data-normalize-split-v1`은 merged PR #4 이후 `CLEANUP_CANDIDATE`
- `feat/annotation-audit-v1`은 merged PR #5 이후 `CLEANUP_CANDIDATE`

| Workstream | Canonical branch / PR | 상태 | Owner / Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | owner 없음 / lease 없음 | 2026-09-08 | 기존 foundation 유지 |
| Nongtori Design Freeze v1 | `main` | DESIGN_FROZEN / DATA_WIP | owner 없음 / canonical docs | 2026-09-10 | label semantics, farm/session 경계, incremental ingestion/revision semantics를 canonical로 유지 |
| Canonical application source 편입 | `main` / merged PR #2 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-10 | 운영센터 application baseline 유지 |
| AI Data Pipeline v1 Core | `main` / merged PR #3 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-10 | Dataset Registry/provider/audit baseline 유지 |
| Normalize / Dedup / Split / Training Snapshot v1 | `main` / merged PR #4 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-10 | label normalize, exact dedup, atomic split, immutable snapshot baseline 유지 |
| Farm-scoped Data Ingestion Design | `main` / merged PR #5 + follow-up main docs | DESIGN_FROZEN | owner 없음 / canonical docs | 2026-09-10 | 초기 baseline 1회 + incremental scan/change detection + append-only revision + content-hash asset reuse + operator data center |

## 현재 canonical workstream

```text
Incremental Ingestion Scanner / Change Detector / Revision Ledger
+ Field Task Audit
+ Farm-scoped Rename Manifest
+ DATA-RIP-001 / DATA-RIP-002 Annotation Audit
→ Actual Normalized Manifest
→ Actual Dedup / Split
→ Training Snapshot v001
→ Baseline Model
→ Optuna
```

핵심 정책:
- Google Sheet/원본 사진·영상은 read-only canonical source
- 최초 1회 baseline 이후 전체 재복사 금지
- 이후 source는 비교를 위해 읽되 NEW/UPDATED/REMOVED/UNCHANGED를 판정
- NEW/UPDATED만 저장/복사
- UPDATED는 기존 revision SUPERSEDED + 새 revision ACTIVE
- REMOVED는 물리 삭제하지 않고 REMOVED_FROM_SOURCE
- 동일 content SHA-256 asset은 재복사하지 않고 재사용
- 최소 데이터 경계는 `farm_id + capture_session_id`
- 사진 rename은 `Original_No exact → EXIF 보조 → order fallback`
- blocking mismatch가 있으면 rename 중단
- Training Snapshot은 physical full copy가 아니라 revision/hash 집합 manifest
- private raw/source/revision payload는 Git에 넣지 않음

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
- branch가 5개면 새 branch 생성 금지
- merged branch는 cleanup candidate로 분류
- 기준 상태 보존은 backup branch보다 tag 우선

## 데이터 안전

Google Sheets/외부 원본/현장 사진·영상은 read-only source다. 기존 revision과 asset은 덮어쓰지 않는다. 학습/평가는 latest eligible ACTIVE revision을 선택해 immutable Training Snapshot manifest로 고정한다.
