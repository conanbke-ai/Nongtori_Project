# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch 확인 기준: `main`, `feat/ai-data-pipeline-v1` = 2/5
- `feat/ai-data-pipeline-v1`은 merged PR #3 이후 `CLEANUP_CANDIDATE`

| Workstream | Canonical branch / PR | 상태 | Owner / Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | owner 없음 / lease 없음 | 2026-09-08 | theme/token, 모바일 접근성, cat jelly paw cursor contract를 baseline으로 유지. 동일 foundation 재구현 금지. |
| Nongtori Design Freeze v1 | `main` | DESIGN_FROZEN / DATA_WIP | owner 없음 / canonical docs | 2026-09-10 | `DESIGN_FREEZE_V1.md` 및 연결 정책 문서 반영·재조회 검증 완료. 구조적 정책 변경 시 Design Review 재오픈. |
| Canonical application source 편입 | `main` / merged PR #2 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-08 / 2026-09-10 | 운영센터 application source, 병해충 확장, 수확일지/판독 협업, 공통 커서, DB/migration, tests, price-forecast scaffold를 main baseline으로 편입 완료. 브라우저 visual/mobile/E2E·실사용자 왕복·모델 성능 검증은 별도 후속 검증 항목으로 유지. |
| AI Data Pipeline v1 Core | `main` / merged PR #3 | MERGED_BASELINE | owner 없음 / lease 종료 | 2026-09-10 | Dataset Registry, Mendeley/HuggingFace/Direct HTTP/Kaggle/AI-Hub adapter, streamed checksum download, safe extraction, audit manifest, immutable provenance snapshot, CLI, source records, unit tests/CI를 main baseline으로 편입 완료. |

## 다음 canonical workstream

```text
Annotation / Label Audit
→ Normalize
→ Dedup
→ Split Manifest
→ Training Snapshot
→ Baseline Model
→ Optuna
```

현재 외부 표본 자동수집 core는 완료되었고, 다음 단계에서는 DATA-RIP-001/002의 실제 annotation/class 구조를 audit한 뒤 Nongtori label mapping version을 확정한다. `APPROVED / NORMALIZED / SNAPSHOT_READY` 상태는 이 단계를 통과하기 전에는 부여하지 않는다.

새 AI/data 구현은 `docs/DESIGN_FREEZE_V1.md`와 연결 정책 문서를 기준으로 한다.

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

앱/병해충/판독/운영센터와 AI data pipeline core baseline은 이제 `main`이다. 같은 기능을 별도 branch에서 재구현하지 않는다.

AI/data pipeline 신규 구현은 Design Freeze 계약을 기준으로 하고, 구조적 의미를 바꾸는 변경이면 코드보다 먼저 Design Review를 다시 연다.

## Branch hygiene

- 동일한 농장/작업자/권한/다국어/UI/병해충 기능을 다른 대화창에서 다시 branch로 만들지 않는다.
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

같은 핵심 경로에 active writer/lease를 2개 두지 않는다. 다른 세션의 lease가 있으면 기존 workstream에 합류하거나 정식 handoff 후 작업한다. 대화가 바뀌었다는 이유만으로 새 branch를 만들지 않는다.

## Stale 정책

- 7일 이상 활동 없음: 필요성/owner 상태 검토
- 14일 이상 활동 없음: `LONG_RUNNING` 유지 사유가 없으면 `CLEANUP_CANDIDATE`
- stale lease는 자동 탈취하지 않는다.

## 데이터 안전

Google Sheets/외부 원본 데이터는 read-only working source로 유지하며, 새 세션에서 임의 더미/대체 데이터 구조를 다시 만들지 않는다. 학습/평가는 immutable snapshot만 사용한다.
