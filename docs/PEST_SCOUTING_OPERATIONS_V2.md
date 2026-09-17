# Nongtori Pest Scouting Operations V2

Status: **CANONICAL / IMPLEMENTED ON MAIN (PR #32)**

이 문서는 `PEST_SCOUTING_STATE_DESIGN.md`의 운영 lifecycle을 보완한다. 기존 stateful scouting 원칙을 유지하며, 현장 입력 정정·case 종료/재발·freshness policy·observation scope validation을 정의한다.

## 1. 현장 입력 정정은 삭제가 아니라 correction event

`scouting_field_checks`는 append-only 원본 관찰 이력이다. 사용자가 잘못 누른 경우 원본 row를 수정/삭제하지 않는다.

```text
FIELD_CHECK(original)
  ↓
FIELD_CHECK_CORRECTION(REPLACE | VOID)
  ↓
현재 state projection 재계산
```

V2 correction 규칙:

- `REPLACE`: 기존 현장 점검의 evidence를 다른 evidence로 교체해 해석한다.
- `VOID`: 잘못 생성한 현장 점검을 무효화한다.
- correction 자체도 actor/time/reason을 보존한다.
- 학습/분석에서는 raw check와 effective check를 구분한다.
- UI는 직전 입력 직후 `입력 수정`을 제공하되 과거 원본은 삭제하지 않는다.

## 2. RESOLVED는 명시적 종료

V2에서는 임의의 일수/횟수 threshold로 case를 자동 종료하지 않는다.

```text
OPEN / MONITORING / POST_TREATMENT
  ↓ user/system explicit resolve action
RESOLVED
```

종료 reason 후보:

```text
NO_FURTHER_ABNORMALITY
TREATMENT_COMPLETED
FALSE_ALARM_CLOSED
OTHER
```

`RESOLVED` 시:

- `scouting_cases.status = RESOLVED`
- `closed_at`, `close_reason` 기록
- `scouting_location_states.current_state = RESOLVED`
- `active_case_id = NULL`
- 과거 observation/check/action은 보존

## 3. 재발은 기존 case 재오픈이 아니라 새 case

RESOLVED 이후 같은 location에서 의미 있는 anomaly가 다시 발생하면 과거 case를 되살리지 않는다.

```text
CASE-A RESOLVED
      ↓ new meaningful anomaly
CASE-B OPEN
previous_case_id = CASE-A
```

이렇게 해야 한 구역의 반복 발생 횟수와 방제 후 재발 패턴을 별도 episode로 분석할 수 있다.

## 4. Field-check freshness는 versioned policy

현재 field data로 `3일`, `7일` 같은 고정 숫자를 근거 없이 freeze하지 않는다.

DB policy profile:

```text
policy_version
freshness_mode
field_check_freshness_minutes nullable
status
```

초기값:

```text
freshness_mode = CALIBRATION_PENDING
field_check_freshness_minutes = NULL
```

운영 의미:

- duration이 calibration으로 확정되면 새 policy version을 생성한다.
- 과거 observation에는 당시 적용된 policy version을 남긴다.
- duration이 NULL인 동안 기존 semantic freshness signal을 사용할 수 있으나 source를 `UPSTREAM_SEMANTIC`으로 기록한다.
- 숫자가 설정된 version부터는 `last_field_check_at`과 observation time을 이용해 runtime이 freshness를 계산한다.

기존 policy row를 소급 수정하지 않는다.

## 5. Observation scope validation

`farm_id + house_id + bed_id + zone_id`를 authoritative location scope로 본다.

관측에 다음 reference가 있으면 저장 전에 검증한다.

### capture_session_id

- 해당 session의 `farm_id`가 요청 farm과 같아야 한다.
- session에 house/bed/zone이 지정되어 있으면 요청 location과 충돌하면 안 된다.

### frame_id

- frame이 속한 capture session의 farm이 요청 farm과 같아야 한다.
- 요청 `capture_session_id`가 함께 오면 frame의 session과 같아야 한다.
- `frame_location_assignments`가 존재하면 assignment의 house/bed/zone과 요청 location이 충돌하면 안 된다.
- assignment가 없으면 capture session location을 fallback으로 검증한다.

scope mismatch는 observation을 저장하지 않고 `SYSTEM_EXCEPTION` 성격의 입력 오류로 처리한다.

## 6. Current state projection 원칙

정정이나 종료는 history 삭제가 아니라 projection 변경이다.

```text
Raw history: immutable
Effective interpretation: latest valid correction 적용
Current state: effective interpretation + lifecycle event로 projection
```

정정 후 state는 교정된 evidence에 맞춰 즉시 갱신한다. `NO_VISIBLE_EVIDENCE`로 교정되어도 `MITE_NEGATIVE`로 변환하지 않는다.

## 7. UI

현장 작업자 기본 동선:

```text
오늘 확인할 곳
→ 현장 점검 결과 1회 탭
→ 필요 시 조치 1회 탭
→ 잘못 눌렀다면 직전 입력 수정
```

case 종료는 별도 `종료` 액션으로 제공하며 방제 버튼 자체가 자동 종료를 의미하지 않는다.

`방제` 후 기본 상태는 `POST_TREATMENT`; 이후 관측은 계속 저장한다.

## 8. Freeze

V2에서 다음을 freeze한다.

- 현장 점검 원본 row 삭제/덮어쓰기 금지
- correction은 append-only event
- case 종료는 명시적 lifecycle event
- RESOLVED 이후 새 anomaly는 새 case
- 새 case는 이전 resolved case를 `previous_case_id`로 연결 가능
- freshness duration은 calibration 전 NULL
- policy는 versioned immutable semantics
- capture/frame reference가 location scope와 충돌하면 observation 저장 금지
- 방제 기록만으로 case 자동 RESOLVED 금지
