# Pest Scouting UX / Runtime Hardening — 2026-09-16

Status: **CANONICAL EXTENSION**

이 문서는 `PEST_SCOUTING_STATE_DESIGN.md`와 `PEST_SCOUTING_DB_SCHEMA_V1.md`의 구현 후 검수에서 확인된 UX/runtime 보완사항을 고정한다.

## 1. 오늘 확인할 곳 = 사람의 입력이 지금 필요한 구역

`오늘 확인할 곳`은 전체 상태 목록이 아니라 actionable queue다.

포함:

```text
FIELD_CHECK_REQUIRED
SUSPECTED
CONFIRMED
```

기본 제외:

```text
WATCH
POST_TREATMENT
MONITORING
RESOLVED
BASELINE
```

`POST_TREATMENT`/`MONITORING`은 상태/history에는 유지하지만 새 변화·악화·재발이 감지되어 `FIELD_CHECK_REQUIRED`로 전이될 때 다시 attention queue에 올린다.

목적:

- 현장 확인을 이미 끝낸 구역이 할 일 목록에 계속 남는 문제 방지
- 방제 직후 같은 조치를 반복하도록 오인하는 문제 방지
- `오늘 확인할 곳`이라는 제품 문구와 실제 동작 일치

## 2. 조치 라벨은 짧은 명사형으로 통일

현장 버튼은 대화체보다 빠르게 스캔 가능한 명사형을 사용한다.

```text
TREATMENT_APPLIED   → 방제
LEAF_REMOVED        → 피해잎 제거
BIOCONTROL_APPLIED  → 천적 처리
OBSERVE_ONLY        → 추적 관찰
OTHER_ACTION        → 기타 조치
```

저장되는 action code는 변경하지 않는다.

## 3. 다국어 UX 일관성

농토리 작업자 UI가 `ko / vi / th / zh-CN`을 지원하므로 scouting queue도 다음까지 언어 전환 대상이다.

- 제목/설명
- 상태명
- 변화 이유
- 최근 현장 확인/최근 조치
- 현장 점검 결과 / 조치 기록
- 빈 상태 / 로딩 / 오류 / 성공 안내
- evidence/action 선택지
- `NO_VISIBLE_EVIDENCE` 의미 설명

한국어 하드코딩을 부분적으로 남겨 언어가 섞이지 않도록 한다.

## 4. Runtime bootstrap parity

Scouting API는 migration이 적용된 운영 DB뿐 아니라 새 로컬/preview DB에서도 동일하게 동작해야 한다.

따라서 scouting runtime bootstrap은 다음을 보장한다.

```text
scouting_issue_catalog
scouting_location_states
scouting_cases
scouting_observations
scouting_field_checks
scouting_actions
scouting_alert_events
```

이 없을 경우 idempotent하게 생성한다.

또한 stateful scouting 활성화 후에는 legacy stateless trigger가 새 DB에서 다시 생성되어서는 안 된다.

```text
frame_predictions → 즉시 MITE_ALERT
```

경로는 runtime bootstrap에서도 비활성 상태를 유지한다.

## 5. 추가 hardening backlog

이번 변경에서 즉시 처리하지 않아도 되는 후속 항목:

- `RESOLVED` 자동/수동 종료 정책과 case close UX
- field-check freshness를 외부 boolean이 아니라 versioned policy에서 계산
- `scouting_alert_events`와 다수 notification outbox 간 1:N 추적 구조
- observation/capture/frame reference의 동일 farm/location scope 검증 강화
- 잘못 누른 현장 입력의 correction event UX
- 실제 브라우저 모바일/데스크톱 visual acceptance

숫자 기반 freshness/해결 기간은 field calibration 전 임의 고정하지 않는다.
