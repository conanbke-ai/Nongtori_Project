# Development rules for AI/code agents

이 저장소에서 ChatGPT, Codex 및 기타 개발 보조도구는 아래 규칙을 항상 우선 적용한다.

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

새 workflow나 배포 자동화를 추가하기 전에 예상 실행 빈도, runtime, 무료 사용량 영향을 반드시 검토한다.
