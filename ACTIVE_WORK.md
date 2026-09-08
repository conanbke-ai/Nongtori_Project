# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 UI foundation: main에 병합 완료

| Workstream | Canonical branch / PR | 상태 | Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | 없음 | 2026-09-08 | theme/token, 모바일 접근성, cat jelly paw cursor contract를 baseline으로 유지. 동일 foundation 재구현 금지. |
| Canonical application source 편입 | `feat/application-source-integration` / PR 예정 | ACTIVE | `app/`, `db/`, `drizzle/`, `public/`, `configs/`, `ml/`, application build config, `README.md`, `ACTIVE_WORK.md`, 편입 문서 | 2026-09-08 / 2026-09-08 | Site 소스 편입, dependency 설치, lint/build, 제한된 secret 패턴 검사 완료. API·권한·모델 regression·모바일/E2E 검증은 미실행. 초안 PR 검토 후 동일 branch에서 검증을 이어간다. [편입 기록](docs/APPLICATION_SOURCE_INTEGRATION.md) 참고. |

## 작업 시작 체크

1. `main` 실제 구현 확인
2. 이 파일 확인
3. open PR 검색
4. branch 수와 ACTIVE workstream 수 확인
5. docs/설계와 기존 asset 확인
6. 수정 예정 경로에 active lease가 있는지 확인
7. `ALREADY_DONE / IN_PROGRESS / NEW` 판정
8. NEW일 때만 Acceptance Criteria 작성 후 branch/lease 확보

## Branch hygiene

- 동일한 농장/작업자/권한/다국어/UI 기능을 다른 대화창에서 다시 branch로 만들지 않는다.
- 같은 목적의 `v2/v3/final/actual/real` branch를 만들지 않는다.
- branch가 5개면 새 branch 생성 금지.
- active workstream이 3개면 새 기능 시작 금지.
- merged branch는 cleanup 후보로 분류하되 실제 삭제는 사용자 승인 후 수행한다.
- 기준 상태 보존은 `backup/*` branch보다 tag를 우선한다.

## Workstream Lease

새 workstream은 반드시 이 표에 다음을 남긴다.

- canonical branch/PR
- 상태
- 수정 예정 핵심 경로
- 시작일/최근 활동일
- Acceptance Criteria

같은 핵심 경로에 active lease를 2개 두지 않는다. 다른 세션의 lease가 있으면 기존 workstream에 합류하거나 선행 통합 후 작업한다.

## Stale 정책

- 7일 이상 활동 없음: 필요성 검토
- 14일 이상 활동 없음: `LONG_RUNNING` 유지 사유가 없으면 `CLEANUP_CANDIDATE`

## 데이터 안전

Google Sheets/외부 원본 데이터는 기존 read-only 원칙을 유지하며, 새 세션에서 임의 더미/대체 데이터 구조를 다시 만들지 않는다.
