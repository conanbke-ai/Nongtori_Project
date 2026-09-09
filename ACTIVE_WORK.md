# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch 확인: `main`, `feat/application-source-integration`, `ui/tori-design-system-v1` = 3/5

| Workstream | Canonical branch / PR | 상태 | Owner / Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | owner 없음 / lease 없음 | 2026-09-08 | theme/token, 모바일 접근성, cat jelly paw cursor contract를 baseline으로 유지. 동일 foundation 재구현 금지. |
| Canonical application source 편입 | `feat/application-source-integration` / Draft PR #2 | ACTIVE / CANONICAL | 기존 PR #2 writer 유지 / `app/`, `db/`, `drizzle/`, `public/`, `configs/`, `ml/`, `tests/`, `vendor/tori-ui/`, application build config 및 관련 docs | 2026-09-08 / 2026-09-09 | 병해충 종류 확장·농장관리 수확일지·판독 기록 협업·운영 현황 UI를 같은 workstream에서 이어간다. API/권한/SQL 통합, overview 표시, type/lint/build 근거는 PR #2에 기록. browser/mobile/E2E·실사용자 왕복·모델 성능 검증은 미실행 항목을 그대로 유지. 새 병해충/운영센터 branch를 만들지 않는다. |

## 작업 시작 체크

1. `main` 실제 구현 확인
2. 이 파일 확인
3. open PR 검색
4. 실제 remote branch 수와 ACTIVE workstream 수 확인
5. docs/설계와 기존 asset 확인
6. 수정 예정 경로에 active lease가 있는지 확인
7. `ALREADY_DONE / IN_PROGRESS / NEW / BLOCKED` 판정
8. NEW일 때만 Acceptance Criteria 작성 후 branch/lease 확보

현재 `feat/application-source-integration` 범위와 겹치는 앱/병해충/판독/운영센터 작업은 `IN_PROGRESS`로 판정하고 PR #2를 이어간다.

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

Google Sheets/외부 원본 데이터는 기존 read-only 원칙을 유지하며, 새 세션에서 임의 더미/대체 데이터 구조를 다시 만들지 않는다.
