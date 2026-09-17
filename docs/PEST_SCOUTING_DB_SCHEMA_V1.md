# Nongtori Pest Scouting DB Schema V1

Status: **CANONICAL / COMPATIBILITY-AWARE TARGET CONTRACT — 2026-09-17**

이 문서는 `PEST_SCOUTING_STATE_DESIGN.md`의 stateful scouting 정책을 실제 DB/runtime에 적용하기 위한 V1 계약이다. 기존 main의 scouting runtime은 보존하며, 공간/현장확인 계약은 아래 목표 구조로 점진 전환한다.

## 1. 원칙

- Observation과 Case를 분리한다.
- 현재 state projection과 append-only history를 분리한다.
- 상태 enum과 병해충 종류를 분리한다.
- 미입력/미확인을 음성 라벨로 만들지 않는다.
- 현장확인은 optional evidence다.
- 농가 공간구조를 `house → bed → zone` 고정 계층으로 만들지 않는다.
- 현재 legacy location column은 destructive migration 없이 compatibility field로 유지할 수 있다.

## 2. 목표 테이블

```text
spatial_units                 # 다농가 가변 공간 hierarchy
scouting_location_states      # 공간별 현재 상태 projection
scouting_cases                # 하나의 의심/발생 episode
scouting_observations         # 자동 관측 append-only
scouting_field_checks         # 현장 확인 event
scouting_field_findings       # 한 확인에서 발견한 0..N finding
scouting_actions              # 조치 event
scouting_alert_events         # 발행/억제/재알림 event
scouting_issue_catalog        # 병해충/질병/환경이상 taxonomy
```

기존 `houses/beds/zones`, `mite_record_notes`, 기존 scouting field-check code는 migration audit 전 삭제하지 않는다.

## 3. spatial_units

농가마다 다른 시설 구조를 지원한다.

```text
id
farm_id
parent_id nullable
unit_type
code
name
display_code
sort_order nullable
metadata_json nullable
active
created_at
updated_at
```

`unit_type` 후보:

```text
FACILITY
HOUSE
SECTION
BLOCK
BED
ROW
ZONE
CUSTOM
```

제약:

```text
UNIQUE(farm_id, id)
UNIQUE(farm_id, display_code)  # 정책상 안정적인 display code를 운영하는 경우
```

`HOUSE`는 필수 레벨이 아니다.

예:

```text
M: 3동 → Bed 08 → E
C1: Facility A → Bed 37 → E
C2: Bed 37 → E
```

## 4. scouting_location_states

빠른 조회를 위한 current projection.

목표 필드:

```text
id
farm_id
spatial_unit_id nullable
location_key                # legacy/derived compatibility key
display_location_code
current_state
active_case_id nullable
last_observed_at nullable
last_field_check_at nullable
last_action_at nullable
last_alert_at nullable
last_alert_reason nullable
baseline_version nullable
recent_pattern_fingerprint nullable
state_version
created_at
updated_at
```

현재 runtime의 다음 필드는 migration 전 유지 가능하다.

```text
house_code
bed_code
zone_code
```

하지만 신규 business logic이 이 세 필드의 존재를 필수 전제로 삼아서는 안 된다.

목표 identity:

```text
farm_id + spatial_unit_id
```

legacy fallback:

```text
farm_id + location_key
```

## 5. scouting_cases

```text
id
farm_id
location_state_id
issue_family
primary_issue_code nullable
status
opened_at
opened_reason
closed_at nullable
close_reason nullable
previous_case_id nullable
created_at
updated_at
```

상태와 이슈를 분리한다.

```text
status = OPEN | MONITORING | POST_TREATMENT | RESOLVED
primary_issue_code = SPIDER_MITE | THRIPS | ... | null
```

동일 observation 반복으로 case를 매번 새로 만들지 않는다.

## 6. scouting_observations

자동/센서/영상/모델 관측을 append-only로 저장한다.

```text
id
farm_id
location_state_id
case_id nullable
capture_session_id nullable
frame_id nullable
source_asset_id nullable
observed_at
source_type
leaf_temp nullable
ambient_temp nullable
reference_temp nullable
humidity nullable
vpd nullable
light_level nullable
thermal_features_json
rgb_reference_json
model_name nullable
model_version nullable
risk_signal nullable
novelty_signal nullable
trend_signal nullable
spatial_signal nullable
pattern_fingerprint nullable
created_at
```

시간정보는 반드시 보존한다. 불규칙 반복 관측에서는 파생 feature로 다음을 만들 수 있다.

```text
time_since_previous
change_since_previous
rolling/accumulated environment features
```

규칙적인 sequence가 없는 데이터를 임의 interpolation해 canonical raw observation처럼 저장하지 않는다.

## 7. scouting_field_checks

현장에 갔다는 event 자체.

```text
id
farm_id
location_state_id
case_id nullable
observation_id nullable
checked_at
recorded_at
checker_member_id nullable
verification_status
note nullable
photo_asset_id nullable
created_at
```

`checked_at`과 `recorded_at`을 구분할 수 있어야 한다. 현장에서 확인한 뒤 나중에 앱에 입력할 수 있기 때문이다.

`verification_status` 목표 enum:

```text
UNVERIFIED      # row가 없는 경우를 기본으로 사용해도 됨
VERIFIED
INCONCLUSIVE
```

현장확인 row가 없다는 사실을 정상/음성으로 변환하지 않는다.

## 8. scouting_field_findings

현장확인의 구체 결과를 0..N으로 저장한다.

```text
id
field_check_id
family
issue_code nullable
finding_code
certainty nullable
severity nullable
created_at
```

`family`:

```text
PEST
DISEASE
PHYSIOLOGICAL_ENVIRONMENTAL
UNKNOWN
NONE_VISIBLE
```

예:

```text
field_check = VERIFIED
finding #1 = PEST / SPIDER_MITE
finding #2 = DISEASE / POWDERY_MILDEW
```

아무 이상을 찾지 못한 경우도 `NONE_VISIBLE`이며 강한 negative ground truth와 동일하지 않다.

현재 runtime의 legacy evidence:

```text
NO_VISIBLE_EVIDENCE
LEAF_DAMAGE_OBSERVED
WEBBING_OR_MITE_TRACE_SUSPECTED
DIRECT_MITE_OR_EGG_CONFIRMED
OTHER_PEST_LIKE_EVIDENCE
DISEASE_LIKE_EVIDENCE
PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY
INCONCLUSIVE
```

은 기존 이력/호환을 위해 보존하고, 신규 도메인에서는 finding mapper를 통해 해석한다.

예:

```text
DIRECT_MITE_OR_EGG_CONFIRMED
→ family=PEST
→ issue_code=SPIDER_MITE
→ state=CONFIRMED
```

## 9. scouting_actions

현장확인과 별도의 event다.

```text
id
farm_id
location_state_id
case_id nullable
action_at
recorded_at
actor_member_id nullable
action_code
detail_json
note nullable
created_at
```

V1 후보:

```text
TREATMENT_APPLIED
LEAF_REMOVED
BIOCONTROL_APPLIED
ENVIRONMENT_ADJUSTED
OBSERVE_ONLY
OTHER_ACTION
```

조치 row가 없으면 `NOT_TREATED`가 아니라 `NO_ACTION_RECORD`로 해석한다.

조치가 있어도 case를 자동 RESOLVED 하지 않는다.

## 10. scouting_alert_events

```text
id
farm_id
location_state_id
case_id nullable
observation_id
created_at
alert_decision
alert_reason
suppression_reason nullable
policy_version
notification_outbox_id nullable
```

`alert_decision`:

```text
ISSUED
SUPPRESSED
ESCALATED
RECHECK_REQUESTED
```

재알림은 의미 있는 변화가 있을 때만 허용한다.

```text
NOVELTY_INCREASE
WORSENING_TREND
SPATIAL_SPREAD
NEW_FIELD_EVIDENCE
STALE_PREVIOUS_CHECK
POST_TREATMENT_REBOUND
```

## 11. scouting_issue_catalog

```text
code
family
display_name_ko
ai_capability
operational_status
created_at
updated_at
```

`family`:

```text
PEST
DISEASE
PHYSIOLOGICAL_ENVIRONMENTAL
UNKNOWN
```

`ai_capability`:

```text
SUPPORTED
ALERT_ONLY
RECORD_ONLY
```

첫 자동 예찰 대상은 응애이지만 schema/UI가 응애 전용이어서는 안 된다.

예:

```text
SPIDER_MITE / PEST / 응애 / ALERT_ONLY
THRIPS / PEST / 총채벌레 / RECORD_ONLY
APHID / PEST / 진딧물 / RECORD_ONLY
POWDERY_MILDEW / DISEASE / 흰가루병 / RECORD_ONLY
UNKNOWN_PEST / PEST / 기타 해충 / RECORD_ONLY
UNKNOWN_DISEASE / DISEASE / 병해 의심 / RECORD_ONLY
ENVIRONMENTAL_STRESS / PHYSIOLOGICAL_ENVIRONMENTAL / 환경·생리 이상 / ALERT_ONLY
```

검증되지 않은 모델은 `SUPPORTED`로 승격하지 않는다.

## 12. UI/API projection

목록 API는 내부 location hierarchy 전체가 아니라 다음처럼 소비하기 쉬운 projection을 제공하는 것을 목표로 한다.

```text
caseId
locationStateId
spatialUnitId nullable
displayLocationCode
primaryIssueCode nullable
currentState
priority
lastObservedAt
repeatCount
summarySignals[]
```

`summarySignals[]` 예:

```text
{ type: HUMIDITY_LOW, label: '습도 낮음', value: '43%' }
{ type: LEAF_TEMP_DELTA, label: '잎 온도 상승', value: '+1.8℃' }
{ type: REPEAT_DETECTION, label: '반복 감지', value: '3회' }
```

UI가 `thermal anomaly high` 같은 모델 내부 문자열을 직접 번역해 보여주지 않도록 한다.

## 13. Compatibility migration 원칙

포트폴리오 V1 완료를 위해 기존 정상 runtime을 파괴적으로 재작성하지 않는다.

단계:

```text
1. Domain/API에서 displayLocationCode + generic finding contract 도입
2. legacy house/bed/zone → Location Adapter 제공
3. spatial_units 추가 migration 설계
4. 신규 데이터부터 spatial_unit_id 병행 저장
5. 기존 데이터 backfill audit
6. 충분히 검증된 후 legacy column deprecation 검토
```

V1에서 3~6을 모두 끝내야 한다는 의미는 아니다.

## 14. Acceptance

- 동일 공간의 observation history가 유지됨
- observation과 CASE가 분리됨
- current state와 history가 분리됨
- 상태와 병해충 종류가 분리됨
- 반복 관측은 저장하면서 alert만 suppress 가능
- 현장 미입력/미관찰을 negative ground truth로 강제 변환하지 않음
- 현장확인과 조치가 별도 event로 저장됨
- 한 현장확인에 여러 finding을 표현 가능
- 응애 외 issue로 확장 가능
- house/bed/zone이 없는 농가 구조도 목표 contract에서 표현 가능
- 기존 runtime/data를 destructive migration 없이 점진 전환 가능
