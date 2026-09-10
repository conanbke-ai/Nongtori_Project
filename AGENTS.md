# Development rules for AI/code agents

이 저장소에서 ChatGPT, Codex 및 기타 개발 보조도구는 아래 규칙을 우선 적용한다.

## Common policy entrypoint

- 공통 정책 canonical은 `conanbke-ai/Tori_Common_Project`다.
- 시작점: `DEVELOPMENT_TEAM_OPERATING_POLICY.md` → `TORI_POLICY_BOOTSTRAP.md` → `POLICY_ROUTER.md`의 필요한 절만 확인한다.
- 제품의 실제 구현 상태는 이 저장소의 최신 `main`, `ACTIVE_WORK.md`, open PR, branch, commit, 실제 코드가 우선한다.

## AI development routing / usage guard

- 사용자가 매 요청마다 Chat/Work/Codex/모델을 선택하게 하지 않는다. 먼저 일반 Chat에서 요구사항·설계·로그/diff/screenshot 분석·Acceptance Criteria·최소 실행 prompt를 가능한 한 끝낸다.
- 실제 repo 수정/빌드/test/git 실행이 필요할 때만 Codex, 실제 browser rendering/route/hover/modal/responsive/interaction 검수가 필요할 때만 Work를 사용한다.
- 공통 라우팅은 `conanbke-ai/Tori_Common_Project`의 `policies/TORI_AI_DEVELOPMENT_ROUTER.md`, 사용량 보호는 `policies/TORI_AGENT_CREDIT_GUARD.md`, UI 최종 검수는 `policies/TORI_UI_VISUAL_QA_STANDARD.md`를 따른다.
- Agent allowance가 없으면 `DEFER_AGENT`로 두고 Chat에서 설계·patch plan·test·실행 prompt를 준비한다.
- 실패 후 동일 prompt를 상위 모델로 반복하지 않는다. 일반 Chat에서 원인을 먼저 분석하고 lowest adequate tier부터 재실행한다.
- UI/디자인은 코드 반영만으로 PASS하지 않는다. 필요한 작업은 실제 렌더링/interaction visual acceptance까지 완료해야 한다.

## Fail-safe core

공통 저장소 접근이 일시적으로 불가능해도 아래는 항상 적용한다.

1. 같은 기능을 다른 branch에서 중복 구현하지 않는다. 먼저 `ALREADY_DONE / IN_PROGRESS / NEW / BLOCKED`를 판정한다.
2. 원격 branch는 `main` 포함 최대 5개, implementation ACTIVE workstream 최대 3개, validation branch 최대 1개를 기본 상한으로 한다.
3. 같은 기능/핵심 경로는 active writer/lease 1개만 허용한다. 대화 교체는 새 branch가 아니라 handoff로 처리한다.
4. 규모 있는 변경은 Acceptance Criteria와 보존할 API/DB/domain contract를 먼저 정한다.
5. 실행하지 않은 test, browser QA, staging, deploy, security review를 PASS/완료라고 보고하지 않는다.
6. server-side authorization, secret/PII 보호, 원본 데이터 보호를 유지한다.
7. branch/data/service 삭제, destructive migration, force/reset, paid overage·유료 설정은 사용자 명시 승인 없이 실행하지 않는다.
8. 로컬 검증을 우선하되 무료량 절약을 이유로 필요한 검증을 삭제하지 않는다.

## Nongtori product contracts

- 아키텍처 기준: `Sensor / Weather / Image / Manual → Adapter → Normalization → Repository → Domain → Analysis Service → Crop/Rule Strategy → API → Farmer UI`.
- 관리자/농장주/작업자 권한과 farm/zone ownership을 UI 편의를 위해 우회하지 않는다.
- Google Sheets 및 외부 원본 데이터는 명시적 요청 없이는 read-only다. 테스트를 위해 원본을 임의 수정·삭제하지 않는다.
- 센서/날씨/이미지/수동 입력은 source, unit, timestamp, missing/outlier 상태와 provenance를 보존한다.
- 병해충은 응애 단일 하드코딩으로 확장하지 않는다. catalog/Strategy/Adapter를 통해 다종 확장 가능하게 유지한다.
- 검증된 inference worker가 없는 병해충에 AI 결과/confidence를 임의 생성하지 않는다.
- 다국어·고령 사용자 UX를 단순화하더라도 실제 기능 의미와 입력 validation을 훼손하지 않는다.
- 실제 앱 구현은 현재 코드와 관련 설계 문서를 기준으로 하며 과거 딸기 프로젝트를 추정 복원하지 않는다.

## UI / TORI family

- 제품 UI 세부 기준은 이 저장소의 관련 docs와 공통 `policies/TORI_UI_SYSTEM_STANDARD.md`를 따른다.
- mobile-first, 최소 44px hit area, 짧고 명확한 상태 표현을 우선한다.
- 표준 농토리 캐릭터와 공통 `고양이 젤리발 + 뾰잉!` 인터랙션 계약을 임의 변경하지 않는다.
- project theme token을 사용하고 거대한 global CSS/JS monolith 또는 화면별 중복 component를 늘리지 않는다.

## Validation ownership

- UI/입력/다국어: 관련 local unit/smoke + 필요 시 browser visual QA.
- 농장/작업/권한/데이터: 관련 service/repository/authorization test.
- DB/runtime 차이가 실제로 필요할 때만 staging을 사용한다.
- 새 workflow나 배포 자동화 전 예상 실행 빈도·runtime·무료 사용량 영향을 확인한다.

작업 종료/중단/인계 시 기존 `ACTIVE_WORK.md` 또는 PR에 branch/PR/SHA, 완료·미완료, 실행한 검증, known issue, 다음 단계를 남긴다.
