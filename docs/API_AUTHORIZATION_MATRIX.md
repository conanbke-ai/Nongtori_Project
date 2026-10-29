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
- non-local 익명 요청은 농장 목록을 받지 못하고, localhost/127.0.0.1 분류는 개발용 코드 경계로만 확인한다.

## 성공 계약 실행 현황

`EXECUTED`는 해당 route를 isolated fixture에서 실제 호출한 경우만 뜻한다. 같은 권한 유형의 대표 경계가 통과했더라도 route 자체를 호출하지 않았으면 `NOT_RUN`이다.

| Handler | 허용 주체 | 상태 | 증거 |
|---|---|---|---|
| `account-profile#PATCH` | 대상 farm의 현재 구성원 본인 | EXECUTED | `api-authorization`: 별명·언어 row 갱신 |
| `alert-reviews#POST` | `reviewAlerts` 구성원 | EXECUTED | `pest-records`: worker review 생성 |
| `community-chat-messages#POST` | 승인된 활성 구성원 | NOT_RUN | route 성공 호출 미실행 |
| `community-chat-messages#DELETE` | 작성자 또는 ADMIN | NOT_RUN | route 성공 호출 미실행 |
| `farm-chat-messages#POST` | 활성 구성원 | EXECUTED | `api-authorization`: worker 메시지 생성 |
| `farm-chat-messages#DELETE` | 작성자 또는 `manageMembers` 구성원 | EXECUTED | `api-authorization`: 작성자 soft delete |
| `farm-members#POST` | `manageMembers`; OWNER는 WORKER만 | EXECUTED | `api-authorization`: 구성원·audit row 생성 |
| `farm-members#PATCH` | `manageMembers`와 대상 역할 제한 | NOT_RUN | route 성공 호출 미실행 |
| `farm-members#DELETE` | `manageMembers`와 대상 역할 제한 | NOT_RUN | route 성공 호출 미실행 |
| `forecast-worker#POST` | `FORECAST_WORKER_TOKEN` | EXECUTED | `api-authorization`: 204 idle 후 job claim |
| `forecast-worker#PUT` | `FORECAST_WORKER_TOKEN` | NOT_RUN | 결과 저장 성공 호출 미실행 |
| `fruit-assessments#POST` | `uploadMedia` 구성원 | NOT_RUN | route 성공 호출 미실행 |
| `fruit-weights#POST` | `uploadMedia`, 같은 farm assessment | EXECUTED | `weight-source`: 수동 계측 저장 |
| `harvest-completion#POST` | `ROBOT_INGEST_TOKEN` | EXECUTED | `api-authorization`: run·grade·forecast job 생성 |
| `harvest-runs#POST` | `uploadMedia` 구성원 | NOT_RUN | route 성공 호출 미실행 |
| `harvest-runs#PATCH` | `uploadMedia` 구성원 | NOT_RUN | route 성공 호출 미실행 |
| `mite-capture#POST` | `uploadMedia` 구성원 | NOT_RUN | wrapper route 성공 호출 미실행 |
| `notification-worker#POST` | `NOTIFICATION_WORKER_TOKEN` | EXECUTED | `api-authorization`: 빈 queue 200, 외부 호출 0 |
| `notifications#POST` | `viewHistory` 구성원 본인 | NOT_RUN | route 성공 호출 미실행 |
| `observations#POST` | `uploadMedia`, 같은 farm assessment | NOT_RUN | route 성공 호출 미실행 |
| `pest-capture#POST` | `uploadMedia` 구성원 | EXECUTED | `pest-records`: catalog target별 접수 |
| `phone-notifications#POST` | 대상 farm의 현재 구성원 본인 | NOT_RUN | 외부 SMS 없는 toggle 성공도 미실행 |
| `record-notes#POST` | record farm의 `viewHistory`/`reviewAlerts` 구성원 | EXECUTED | `pest-records`: owner/worker note·reply |
| `record-notes#PATCH` | 작성자이며 `reviewAlerts` 구성원 | EXECUTED | `pest-records`: 작성자 수정 |
| `record-notes#DELETE` | 작성자 또는 `manageMembers` 구성원 | NOT_RUN | route 성공 호출 미실행 |
| `scouting-actions#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: 처리 조치·상태 전이 |
| `scouting-field-check-corrections#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: append-only 확인 정정 |
| `scouting-field-checks#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: 현장 확인 row 생성 |
| `scouting-observations#POST` | `manageFarm` 구성원 | EXECUTED | `api-authorization`: ADMIN 관측·case 생성 |
| `scouting-resolve#POST` | `reviewAlerts` 구성원 | EXECUTED | `api-authorization`: 진행 case 종료 |
| `vendor/farm-import#POST` | `VENDOR_IMPORT_TOKEN` | EXECUTED | `api-authorization`: read-only fixture import |
| `video-sessions#POST` | `uploadMedia` 구성원 | NOT_RUN | route 성공 호출 미실행 |
| `video-upload#POST` | `uploadMedia`, 같은 farm zone/item | EXECUTED | `api-authorization`: fake R2·session 생성 |

## 남은 검증 범위

- 위 표에서 19개 handler는 성공 route를 직접 실행했고, `NOT_RUN` 14개와 모든 역할 조합은 아직 각각 실행하지 않았다.
- `localhost`와 `127.0.0.1` 분류 및 non-local 익명 차단은 단위 검증했다. URL hostname에 따른 개발 fallback이 실제 운영 hosting에서 활성화되지 않는지는 여전히 미확인이다.
- 실제 D1/R2, 실제 SMS·worker endpoint, 사용자 실데이터는 이 테스트에서 사용하지 않는다.
