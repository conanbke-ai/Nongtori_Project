# Application source 편입 기록 — 2026-09-08

## 출처와 범위

- 작업 판정: `IN_PROGRESS` — 기존 농토리 운영센터의 실제 소스를 이어서 편입.
- GitHub base: `d276c9e76073f16fe0b58faacccd7b89a9e13525`.
- 원본 Site source commit: `fc1608a86518fe7011ec7b96b67d0530b12a7ff3`.
- 작업 branch: `feat/application-source-integration`.
- `app/`, `db/`, `drizzle/`, `configs/`, `ml/`, `public/`, 의존성 lockfile과 build 설정을 편입.
- 기존 저장소 문서와 공식 자산은 유지. Site README는 `docs/APPLICATION.md`로 이동.
- 로그인·대시보드 본문 이미지 경로만 `public/nongtori-tori.webp`로 변경. 해당 파일은 `assets/nongtori-tori.webp`의 동일 사본.
- GitHub main 편입은 PR 병합 후 성립한다. 이번 작업은 기존 Site를 배포하거나 DB migration을 적용하지 않는다.

## Contract와 남은 구조 정리

원본 Site 대비 API route, DB schema/migration, 농장 권한 코드, 가져오기 payload, ML 코드는 변경하지 않았다. Google Sheet 원본 및 field/production 데이터도 읽거나 변경하지 않았다. 신규 농업 수치나 테스트 계정은 생성하지 않았다.

현 소스에는 API에서 DB를 직접 사용하는 구현과 큰 CSS/DB 모듈이 남아 있다. 코드 편입은 목표 Architecture 준수를 완료했다는 의미가 아니다. 후속 기능 변경과 연결된 영역부터 Service/Repository/Adapter/Strategy를 점진적으로 분리한다. Google Sheets 직접 읽기 Adapter와 실제 Sheet column mapping은 후속 작업이며, 기존 snapshot import 계약을 먼저 확인해야 한다.

## 실제 실행한 검증

| 검증 | 결과 | 범위 |
|---|---|---|
| 의존성 설치 | 통과 | 기존 pnpm lockfile 유지 |
| `pnpm lint` | 통과 | 편입 소스 및 공식 이미지 경로 변경 포함 |
| Site build helper → `vinext build` | 통과 | client/server 빌드, 실제 배포 검증 아님 |
| `git diff --check` | 통과 | 편입 diff |
| secret 패턴 검사 | 탐지 없음 | 일부 key/token/개인키/문자열 할당 패턴만 확인한 제한된 검사; 전체 보안감사 아님 |

검증은 로컬 편입 커밋 `2fe2eaa` 작성 전에 실행했다. 이후 문서 정정은 앱 실행 코드·의존성·빌드 설정을 바꾸지 않는다.

## 미실행 및 다음 단계

- Unit/data contract/API/role authorization 테스트: 미실행.
- 모델·규칙 regression 및 Precision/Recall/F1/confusion matrix: 미실행.
- 브라우저·모바일·E2E: 미실행.
- field 검증: 미실행.
- 릴리스 판단 전 API/권한·모바일 smoke와 모델/데이터 gate를 확인한다.
- 이후 동일 canonical 작업에서 Sheet schema 확인, READ ONLY Adapter, 격리된 테스트 농장·계정 연결을 진행한다.
