# 변경 API 권한 매트릭스

이 문서는 변경성 API(`POST`, `PUT`, `PATCH`, `DELETE`)가 사용하는 서버 권한 경계를 분류한다.
실제 권한 판정은 각 route와 `app/lib/farm-auth.ts`가 기준이며, 이 표는 누락 감시와 회귀 검증을 위한 인덱스다.

## 경계 유형

- `FARM_MEMBER`: 요청 identity가 대상 농장의 활성 구성원이며, 작성자·대상 record 범위를 추가 확인한다.
- `FARM_PERMISSION`: 활성 구성원에 더해 `uploadMedia`, `reviewAlerts`, `manageFarm`, `manageMembers` 같은 역할 권한을 요구한다.
- `MEMBER_SELF`: 대상 농장의 현재 구성원 본인 record만 변경한다.
- `SERVICE_TOKEN`: 사용자 세션이 아닌 기능별 worker/vendor token을 요구한다. 로컬 개발 우회는 production 인증 근거가 아니다.

## 현재 분류

| Route | Method | 경계 | 세부 계약 |
|---|---|---|---|
| `account-profile` | PATCH | MEMBER_SELF | 현재 구성원의 별명·언어 |
| `alert-reviews` | POST | FARM_PERMISSION | `reviewAlerts` |
| `community-chat-messages` | POST, DELETE | FARM_MEMBER | 구성원 작성, 작성자 또는 관리자 삭제 |
| `farm-chat-messages` | POST, DELETE | FARM_MEMBER | 구성원 작성, 작성자 또는 관리자 삭제 |
| `farm-members` | POST, PATCH, DELETE | FARM_PERMISSION | `manageMembers`, 대상 역할 제한 |
| `forecast-worker` | POST, PUT | SERVICE_TOKEN | `FORECAST_WORKER_TOKEN` |
| `fruit-assessments` | POST | FARM_PERMISSION | `uploadMedia` |
| `fruit-weights` | POST | FARM_PERMISSION | `uploadMedia`, 대상 과실의 farm 범위 |
| `harvest-completion` | POST | SERVICE_TOKEN | `ROBOT_INGEST_TOKEN` |
| `harvest-runs` | POST, PATCH | FARM_PERMISSION | `uploadMedia` |
| `mite-capture` | POST | FARM_PERMISSION | pest capture의 `uploadMedia` 경계 재사용 |
| `notification-worker` | POST | SERVICE_TOKEN | `NOTIFICATION_WORKER_TOKEN` |
| `notifications` | POST | FARM_MEMBER | 현재 구성원의 수신 상태 |
| `observations` | POST | FARM_PERMISSION | `uploadMedia`, 대상 farm·assessment 범위 |
| `pest-capture` | POST | FARM_PERMISSION | `uploadMedia` |
| `phone-notifications` | POST | MEMBER_SELF | 현재 구성원의 전화 인증·알림 설정 |
| `record-notes` | POST, PATCH, DELETE | FARM_MEMBER | record farm 범위, 작성자 또는 관리 권한 |
| `scouting-actions` | POST | FARM_PERMISSION | `reviewAlerts`, member identity |
| `scouting-field-check-corrections` | POST | FARM_PERMISSION | `reviewAlerts`, member identity |
| `scouting-field-checks` | POST | FARM_PERMISSION | `reviewAlerts`, member identity |
| `scouting-observations` | POST | FARM_PERMISSION | `manageFarm` |
| `scouting-resolve` | POST | FARM_PERMISSION | `reviewAlerts`, member identity |
| `vendor/farm-import` | POST | SERVICE_TOKEN | `VENDOR_IMPORT_TOKEN` |
| `video-sessions` | POST | FARM_PERMISSION | `uploadMedia` |
| `video-upload` | POST | FARM_PERMISSION | `uploadMedia`, item·zone farm 범위 |

## 자동 검증 범위

`tests/api-authorization.test.ts`는 route source에서 모든 변경 핸들러를 찾고 위 분류에 빠진 항목이 있으면 실패한다.
또한 기존 병해충·scouting 음성 테스트에 더해 다음 경계를 isolated in-memory fixture로 검증한다.

- 미인증 사용자, 작업자, 다른 농장 사업주는 농장 구성원을 추가할 수 없고 audit row도 남기지 않는다.
- 미인증 사용자와 다른 농장 구성원은 계정 프로필을 바꾸지 못한다.
- 미인증 사용자와 다른 농장 구성원은 영상 업로드 전에 거부되며 R2·capture session을 만들지 않는다.
- 잘못된 worker/vendor token은 forecast, harvest ingest, notification, farm import 변경이나 외부 발송 전에 거부된다.
- 승인된 농장 구성원은 자신의 프로필과 대화를 변경하고, 허용된 역할은 구성원 초대와 영상 접수를 수행한다.
- 올바른 service token은 fixture vendor import, robot harvest ingest, forecast claim, 빈 notification queue까지 도달한다.
- 익명 요청은 URL이 non-local, `localhost`, `127.0.0.1` 중 무엇이든 농장 목록이나 구성원 권한을 받지 못한다.
- loopback URL도 실제 Sites identity가 가리키는 활성 membership 범위에서만 접근하며 다른 농장으로 확장되지 않는다.
- `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`와 request hostname은 농장 또는 worker/vendor 권한 근거로 사용하지 않는다.
- 필수 worker/vendor token binding이 없거나 token이 틀린 요청은 loopback URL에서도 DB 쓰기나 외부 호출 전에 `401` 또는 capability-unconfigured `503`으로 닫힌다. 유효 token은 같은 production handler 정상 경로에 도달한다.

## Hostname-independent authentication boundary

- Farm identity는 Sites가 전달한 identity header와 활성 `farm_members` row의 일치로만 성립한다. loopback hostname은 첫 구성원 선택이나 synthetic ADMIN을 만들지 않는다.
- Dashboard farm selection은 공통 `getAccessibleFarms`를 사용하므로 별도의 localhost 전체-farm query가 없다.
- Forecast, notification, robot-ingest, vendor import는 공통 service-token decision을 사용하고 hostname을 입력으로 받지 않는다. 각 route의 기존 missing-token `401`/`503` 계약은 유지한다.
- 신뢰 가능한 client/network marker가 없으므로 production 코드에 local-preview auth flag나 test-only 우회를 추가하지 않았다. local preview도 Sites identity와 실제 membership 또는 정상 service token이 필요하다.
- 설치된 production 경로의 정적 검토에서는 Cloudflare router와 vinext가 `request.url`을 보존한다. 운영 원격 ADMIN 우회는 입증되지 않았으며, OpenAI hosting upstream/live behavior는 계속 `NOT_RUN`이다.

## 성공 계약 실행 현황

`EXECUTED`는 해당 route를 isolated fixture에서 실제 호출한 경우만 뜻한다. 같은 권한 유형의 대표 경계가 통과했더라도 route 자체를 호출하지 않았으면 `NOT_RUN`이다. 이는 handler당 정상 권한 분기 1개의 smoke/contract 실행 상태이며 모든 action·role 분기나 전체 제품 acceptance를 뜻하지 않는다.

| Handler | 허용 주체 | 상태 | 증거 |
|---|---|---|---|
| `account-profile#PATCH` | 대상 farm의 현재 구성원 본인 | EXECUTED | `api-authorization`: 별명·언어 row 갱신 |
| `alert-reviews#POST` | `reviewAlerts` 구성원 | EXECUTED | `pest-records`: worker review 생성 |
| `community-chat-messages#POST` | 승인된 활성 구성원 | EXECUTED | `api-authorization`: 승인 worker 메시지 생성 |
| `community-chat-messages#DELETE` | 작성자 또는 ADMIN | EXECUTED | `api-authorization`: 작성자 soft delete |
| `farm-chat-messages#POST` | 활성 구성원 | EXECUTED | `api-authorization`: worker 메시지 생성 |
| `farm-chat-messages#DELETE` | 작성자 또는 `manageMembers` 구성원 | EXECUTED | `api-authorization`: 작성자 soft delete |
| `farm-members#POST` | `manageMembers`; OWNER는 WORKER만 | EXECUTED | `api-authorization`: 구성원·audit row 생성 |
| `farm-members#PATCH` | `manageMembers`와 대상 역할 제한 | EXECUTED | `api-authorization`: ADMIN의 격리 구성원 이름·역할 변경과 audit 생성 |
| `farm-members#DELETE` | `manageMembers`와 대상 역할 제한 | EXECUTED | `api-authorization`: ADMIN의 격리 구성원 삭제·대기 알림 취소·audit 보존 |
| `forecast-worker#POST` | `FORECAST_WORKER_TOKEN` | EXECUTED | `api-authorization`: 204 idle 후 job claim |
| `forecast-worker#PUT` | `FORECAST_WORKER_TOKEN` | EXECUTED | `api-authorization`: 공급된 fixture 예측 저장·job 완료, 모델 미실행 |
| `fruit-assessments#POST` | `uploadMedia` 구성원 | EXECUTED | `api-authorization`: memory FILES stub과 과실 평가·세션 저장 |
| `fruit-weights#POST` | `uploadMedia`, 같은 farm assessment | EXECUTED | `weight-source`: 수동 계측 저장 |
| `harvest-completion#POST` | `ROBOT_INGEST_TOKEN` | EXECUTED | `api-authorization`: run·grade·forecast job 생성 |
| `harvest-runs#POST` | `uploadMedia` 구성원 | EXECUTED | `api-authorization`: worker 수확 작업 시작 |
| `harvest-runs#PATCH` | `uploadMedia` 구성원 | EXECUTED | `api-authorization`: worker 수확 작업 완료 |
| `mite-capture#POST` | `uploadMedia` 구성원 | EXECUTED | `api-authorization`: legacy MITE wrapper 접수·추론 미생성 |
| `notification-worker#POST` | `NOTIFICATION_WORKER_TOKEN` | EXECUTED | `api-authorization`: 빈 queue 200, 외부 호출 0 |
| `notifications#POST` | `viewHistory` 구성원 본인 | EXECUTED | `api-authorization`: 본인 알림 read 상태 갱신 |
| `observations#POST` | `uploadMedia`, 같은 farm assessment | EXECUTED | `api-authorization`: memory FILES stub과 RGB·열화상 관측·asset 저장 |
| `pest-capture#POST` | `uploadMedia` 구성원 | EXECUTED | `pest-records`: catalog target별 접수 |
| `phone-notifications#POST` | 대상 farm의 현재 구성원 본인 | EXECUTED | `api-authorization`: 외부 SMS 없이 본인 알림 toggle 비활성화 |
| `record-notes#POST` | record farm의 `viewHistory`/`reviewAlerts` 구성원 | EXECUTED | `pest-records`: owner/worker note·reply |
| `record-notes#PATCH` | 작성자이며 `reviewAlerts` 구성원 | EXECUTED | `pest-records`: 작성자 수정 |
| `record-notes#DELETE` | 작성자 또는 `manageMembers` 구성원 | EXECUTED | `api-authorization`: 작성자 메모 soft delete |
| `scouting-actions#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: 처리 조치·상태 전이 |
| `scouting-field-check-corrections#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: append-only 확인 정정 |
| `scouting-field-checks#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: 현장 확인 row 생성 |
| `scouting-observations#POST` | `manageFarm` 구성원 | EXECUTED | `api-authorization`: ADMIN 관측·case 생성 |
| `scouting-resolve#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: 진행 case 종료 |
| `vendor/farm-import#POST` | `VENDOR_IMPORT_TOKEN` | EXECUTED | `api-authorization`: fixture source를 in-memory DB에 import하여 farm 생성 |
| `video-sessions#POST` | `uploadMedia` 구성원 | EXECUTED | `api-authorization`: worker 개인 촬영 세션 등록 |
| `video-upload#POST` | `uploadMedia`, 같은 farm zone/item | EXECUTED | `api-authorization`: fake R2·session 생성 |

## 남은 검증 범위

- 위 표의 33개 handler 모두 isolated fixture에서 정상 권한 분기 1개 이상을 직접 실행했다(`EXECUTED` 33/33, `NOT_RUN` 0/33). 이는 전체 기능 완성이나 제품 acceptance가 아니다.
- 33/33 제한: `phone-notifications`는 외부 SMS 없는 알림 비활성화만, `forecast-worker#PUT`은 모델 실행 없이 공급된 fixture 예측의 저장만, 파일 route는 in-memory `FILES` stub만 검증했다. 실제 SMS·모델 연동·R2·production D1과 각 handler의 나머지 action·role 분기는 별도 branch-level `NOT_RUN`이며 handler-row `NOT_RUN` 0/33 집계에는 포함되지 않는다.
- loopback/non-local 익명 차단, loopback의 실제 membership scope, proxy-header 비승격, 필수 token binding 부재와 잘못된 token의 fail-closed 동작, 유효 token 정상 경로를 production handler로 단위 검증했다. Source regression은 권한 코드에 loopback hostname 신뢰가 다시 추가되면 실패한다. OpenAI hosting upstream/live behavior는 branch-level `NOT_RUN`이다.
- 실제 D1/R2, 실제 SMS·worker endpoint, 사용자 실데이터는 이 테스트에서 사용하지 않는다. 파일 route는 in-memory `FILES` stub만 사용하고, 외부 `fetch`는 호출 시 실패하도록 막아 0건을 확인한다.
