# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch 확인 기준: `main`, `feat/ai-data-pipeline-v1`, `feat/data-normalize-split-v1`, `feat/annotation-audit-v1` = 4/5
- `feat/ai-data-pipeline-v1`은 merged PR #3 이후 `CLEANUP_CANDIDATE`
- `feat/data-normalize-split-v1`은 merged PR #4 이후 `CLEANUP_CANDIDATE`

| Workstream | Canonical branch / PR | 상태 | Owner / Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | owner 없음 / lease 없음 | 2026-09-08 | theme/token, 모바일 접근성, cat jelly paw cursor contract를 baseline으로 유지. 동일 foundation 재구현 금지. |
| Nongtori Design Freeze v1 | `feat/annotation-audit-v1` | DESIGN_UPDATE / ACTIVE | 현재 세션 / data ingestion + annotation audit docs/code | 2026-09-10 | 원본 보호, farm/capture-session 경계, 운영자 데이터 관리센터, Working Copy/rename audit 설계를 canonical 문서에 반영하고 이후 실제 ingestion/audit 구현으로 이어간다. |
| Canonical application source 편입 | `main` / merged PR #2 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-08 / 2026-09-10 | 운영센터 application source, 병해충 확장, 수확일지/판독 협업, 공통 커서, DB/migration, tests, price-forecast scaffold를 main baseline으로 편입 완료. |
| AI Data Pipeline v1 Core | `main` / merged PR #3 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-10 | Dataset Registry, provider adapters, audit manifest, provenance snapshot, CLI, unit tests/CI를 main baseline으로 편입 완료. |
| Normalize / Dedup / Split / Training Snapshot v1 | `main` / merged PR #4 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-10 | Field/External normalize, harvest target, exact dedup, atomic split/leakage guard, immutable training snapshot baseline 완료. |

## 현재 canonical workstream

```text
Field Task Audit
+ Farm-scoped Ingestion / Rename Manifest
+ DATA-RIP-001 / DATA-RIP-002 Annotation Audit
→ Actual Normalized Manifest
→ Actual Dedup / Split
→ Training Snapshot v001
→ Baseline Model
→ Optuna
```

핵심 정책:
- Google Sheet/원본 사진·영상은 read-only canonical source
- 학습/파일명 정리는 export snapshot/Working Copy에서 수행
- 최소 데이터 경계는 `farm_id + capture_session_id`
- 사진 rename은 `Original_No exact → EXIF 보조 → order fallback`
- blocking mismatch가 있으면 rename 전체 중단
- 농민/작업자 화면과 운영자 데이터 관리센터를 분리
- private raw/source snapshot은 Git에 넣지 않음

새 AI/data 구현은 `docs/DESIGN_FREEZE_V1.md`, `docs/LABEL_MAPPING_POLICY.md`, `docs/DATA_INGESTION_MANAGEMENT.md`와 연결 정책 문서를 기준으로 한다.

## 작업 시작 체크

1. `main` 실제 구현 확인
2. `docs/DESIGN_FREEZE_V1.md` 상태 확인
3. 이 파일 확인
4. open PR 검색
5. 실제 remote branch 수와 ACTIVE workstream 수 확인
6. docs/설계와 기존 asset 확인
7. 수정 예정 경로에 active lease가 있는지 확인
8. `ALREADY_DONE / IN_PROGRESS / NEW / BLOCKED` 판정
9. NEW일 때만 Acceptance Criteria 작성 후 branch/lease 확보

## Branch hygiene

- 같은 목적의 `v2/v3/final/actual/real` branch를 만들지 않는다.
- branch가 5개면 새 branch 생성 금지.
- active workstream이 3개면 새 기능 시작 금지.
- merged branch는 cleanup 후보로 분류하되 실제 삭제는 사용자 승인과 unique commit 확인 후 수행한다.
- 기준 상태 보존은 `backup/*` branch보다 tag를 우선한다.

## Workstream Lease / Handoff

새 workstream은 반드시 다음을 남긴다.
- canonical branch/PR
- status
- owner/session
- 수정 예정 핵심 경로 또는 domain
- Acceptance Criteria
- dependency/blocker
- 실행한 검증과 NOT_RUN 항목

같은 핵심 경로에 active writer/lease를 2개 두지 않는다.

## 데이터 안전

Google Sheets/외부 원본 데이터는 read-only working source로 유지한다. 원본 사진/영상도 기본적으로 직접 수정하지 않는다. 학습/평가는 immutable source/training snapshot과 validated Working Copy를 사용한다.
