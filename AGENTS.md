# Development rules for AI/code agents

이 저장소에서 ChatGPT, Codex 및 기타 개발 보조도구는 아래 규칙을 항상 우선 적용한다.

## 작업 조정 / 중복 개발 방지

1. 코드 수정 전에 반드시 `main`, `ACTIVE_WORK.md`, open PR, 관련 branch, 최근 commit을 먼저 확인한다.
2. 새 작업은 `ALREADY_DONE / IN_PROGRESS / NEW` 중 하나로 판정한 뒤 시작한다.
3. 동일 기능의 기존 canonical branch/PR이 있으면 새 branch를 만들지 않고 기존 workstream을 이어간다.
4. 동일 목적의 `v2`, `v3`, `final`, `actual`, `real` branch 반복 생성을 금지한다.
5. open PR의 changed files와 수정 예정 파일이 겹치면 별도 branch에서 병렬 수정하지 않는다.
6. main 또는 active PR에 이미 구현된 기능은 다시 개발하지 않는다. 검수·보완·리팩토링만 한다.
7. 한 기능/화면/도메인에는 원칙적으로 하나의 active workstream만 둔다.
8. 작업 시작/종료/병합 시 `ACTIVE_WORK.md`를 갱신한다.
9. 브랜치 삭제/정리는 사용자 승인 없이 하지 않는다. obsolete/duplicate/superseded 후보를 먼저 식별한다.
10. 새 branch 생성은 완전히 독립된 신규 기능이고 기존 workstream과 충돌하지 않을 때만 허용한다.

## 비용/무료 사용량 정책

1. GitHub Actions, Render, 외부 API/AI, DB 등 사용량 기반 리소스는 월간 예산으로 취급한다.
2. 로컬에서 가능한 테스트/검증은 로컬 실행을 우선한다.
3. hosted CI는 fast gate 중심으로 최소화하고, 브라우저/E2E/대량 데이터 검증은 수동 또는 release gate로 분리한다.
4. `push + pull_request` 중복 실행을 만들지 않는다. concurrency cancel, path filter, dependency cache를 사용한다.
5. Render staging/validation은 매 commit 자동 배포하지 않는다. 로컬 검증 후 실제 DB/HTTP/runtime 검증이 필요할 때만 배포한다.
6. 외부 API/AI/브라우저 자동화/대량 검증은 작은 표본으로 선검증 후 필요할 때만 확대한다.
7. 무료량이 부족하거나 소진되어도 개발이 멈추지 않도록 local fallback을 유지한다.
8. 비용 발생, paid overage, 유료 플랜, spend limit 상향, 자동 사용량 증가 설정은 사용자 명시 승인 없이 활성화하지 않는다.
9. 품질을 희생해 테스트를 삭제하지 않는다. fast/risk/full/release 계층으로 분리한다.
10. 코드 변경 전에 변경 유형과 필요한 최소 검증을 먼저 판단한다.

## Nongtori 적용 원칙

- UI/입력/다국어 변경: 관련 로컬 unit/smoke 우선
- 농장/작업/권한/데이터 변경: 관련 service/repository/authorization 테스트 우선
- Google Sheets/외부 데이터는 원본 수정 금지, 읽기 전용 검증을 기본으로 한다.
- 실제 DB/배포환경 차이가 필요한 경우에만 staging 검증을 사용한다.

## TORI UI 구현 규칙

- `docs/TORI_UI_REBUILD.md`와 TORI 패밀리 공통 UI 기준을 실제 앱 구현의 출발점으로 사용한다.
- 현재 저장소는 아직 구현 코드보다 설계 문서 중심이므로 오래된 화면 구조를 새 앱에 복제하지 않는다.
- 모바일 우선, 최소 44px hit area, 고령 농장주 및 외국인 작업자가 빠르게 이해할 수 있는 짧은 문구와 명확한 상태를 우선한다.
- 표준 농토리 캐릭터 asset을 임의 캐릭터로 바꾸지 않는다.
- desktop 커서는 TORI 패밀리 공통 `고양이 젤리발 + 뾰잉!`을 사용한다. 곰발처럼 넓고 두꺼운 중앙 패드는 금지한다.
- 하늘색 토리/field green/strawberry coral 중심 theme token을 사용하고 화면별 임의 색상 복붙을 피한다.
- 거대한 global CSS/JS monolith를 처음부터 만들지 말고 token/primitive/feature module로 분리한다.
- 관리자/농장주/작업자 권한과 외부 원본 데이터 read-only 정책을 UI 편의를 위해 우회하지 않는다.

새 workflow나 배포 자동화를 추가하기 전에 예상 실행 빈도, runtime, 무료 사용량 영향을 반드시 검토한다.
