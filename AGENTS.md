# Development rules for AI/code agents

이 저장소에서 ChatGPT, Codex 및 기타 개발 보조도구는 아래 규칙을 항상 우선 적용한다.

## 공통 팀 운영 정책

- 공통 정책은 `conanbke-ai/Tori_Common_Project`의 [DEVELOPMENT_TEAM_OPERATING_POLICY.md](https://github.com/conanbke-ai/Tori_Common_Project/blob/main/DEVELOPMENT_TEAM_OPERATING_POLICY.md)를 고정 진입점으로 사용한다. 해당 저장소의 TORI_POLICY_BOOTSTRAP.md와 POLICY_ROUTER.md를 통해 필요한 상세 기준만 확인한다.
- 각 대화창/에이전트는 독립 팀원으로 간주하며, 대화 기억보다 저장소의 `main`, `ACTIVE_WORK.md`, open PR, branch, commit 상태를 우선한다.
- 코드 수정 전 반드시 `main -> ACTIVE_WORK.md -> open PR -> branch budget -> recent commits -> changed files/path lease -> ALREADY_DONE/IN_PROGRESS/NEW/BLOCKED` 순서로 Preflight한다.
- 전체 branch는 `main` 포함 최대 5개, ACTIVE workstream 최대 3개, validation branch 최대 1개를 기본 한도로 한다.
- 같은 기능/화면/도메인과 같은 핵심 파일/경로에는 active workstream/lease를 1개만 둔다.
- 동일 기능의 기존 canonical branch/PR이 있으면 새 branch를 만들지 않는다.
- `v2/v3/final/final2/actual/real/implementation/new` 식의 동일 목적 branch 증식을 금지한다.
- branch budget이 가득 차면 새 branch를 만들지 않고 기존 작업을 먼저 merge/close/supersede/cleanup한다.
- 규모 있는 작업은 구현 전에 Acceptance Criteria, 보존 contract, dependency, 필요한 test를 정한다.
- 다른 workstream이 소비하는 API/DB/event/state/shared type 계약을 바꿀 때는 영향받는 PR/call site를 먼저 확인하고 silent breaking change를 금지한다.
- main이 계속 움직일 때 무한 rebase를 반복하지 않고 Integration Window에서 dependency 순서대로 동기화/검증/merge한다.
- 작업을 넘길 때 branch/PR/SHA, 완료/미완료, 테스트 여부, known issue, 다음 작업을 명확히 handoff한다.
- merge 후 `ACTIVE_WORK.md`를 갱신하고 merged/obsolete branch를 cleanup 후보로 분류한다.
- 브랜치/데이터/서비스 삭제, destructive migration, force push 등 파괴적 작업은 사용자 승인 없이 실행하지 않는다.

## 비용/무료 사용량 정책

1. GitHub Actions, Render, 외부 API/AI, DB 등 사용량 기반 리소스는 월간 예산으로 취급한다.
2. 로컬에서 가능한 테스트/검증은 로컬 실행을 우선한다.
3. hosted CI는 fast gate 중심으로 최소화하고, 브라우저/E2E/대량 데이터 검증은 수동 또는 release gate로 분리한다.
4. `push + pull_request` 중복 실행을 만들지 않는다. concurrency cancel, path filter, dependency cache를 사용한다.
5. Render staging/validation은 매 commit 자동 배포하지 않는다. 로컬 검증 후 실제 DB/HTTP/runtime 검증이 필요할 때만 배포한다.
6. 외부 API/AI/브라우저 자동화/대량 검증은 작은 표본으로 선검증 후 필요할 때만 확대한다.
7. 무료량이 부족하거나 소진되어도 개발이 멈추지 않도록 local fallback을 유지한다.
8. 비용 발생, paid overage, 유료 플랜, spend limit 상향, 자동 사용량 증가 설정은 사용자 명시 승인 없이 활성화하지 않는다.

## Nongtori 적용 원칙

- UI/입력/다국어 변경: 관련 로컬 unit/smoke 우선
- 농장/작업/권한/데이터 변경: 관련 service/repository/authorization 테스트 우선
- Google Sheets/외부 데이터는 원본 수정 금지, 읽기 전용 검증을 기본으로 한다.
- 실제 DB/배포환경 차이가 필요한 경우에만 staging 검증을 사용한다.

## Nongtori 추가 보존 계약

- 관리자/농장주/작업자 권한 모델을 UI 편의를 위해 우회하지 않는다.
- 외부 원본 데이터는 read-only를 기본으로 하고 테스트를 위해 임의 수정하지 않는다.
- 다국어/고령 사용자 UX 변경은 실제 기능 의미와 입력 validation을 단순화하더라도 훼손하지 않는다.
- 실제 앱 구현은 기존 설계/데이터 전략 문서를 먼저 확인하고 같은 모델을 새 branch에서 다시 설계하지 않는다.

## TORI UI 구현 규칙

- `docs/TORI_UI_REBUILD.md`와 TORI 패밀리 공통 UI 기준을 실제 앱 구현의 출발점으로 사용한다.
- 모바일 우선, 최소 44px hit area, 고령 농장주 및 외국인 작업자가 빠르게 이해할 수 있는 짧은 문구와 명확한 상태를 우선한다.
- 표준 농토리 캐릭터 asset을 임의 캐릭터로 바꾸지 않는다.
- desktop 커서는 TORI 패밀리 공통 `고양이 젤리발 + 뾰잉!`을 사용한다.
- 하늘색 토리/field green/strawberry coral 중심 theme token을 사용하고 화면별 임의 색상 복붙을 피한다.
- 거대한 global CSS/JS monolith를 처음부터 만들지 말고 token/primitive/feature module로 분리한다.

새 workflow나 배포 자동화를 추가하기 전에 예상 실행 빈도, runtime, 무료 사용량 영향을 반드시 검토한다.
