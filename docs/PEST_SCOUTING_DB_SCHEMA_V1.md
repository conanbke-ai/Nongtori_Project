# Nongtori Pest Scouting DB Schema V1

Status: **CANONICAL CANDIDATE / IMPLEMENTATION CONTRACT DRAFT**

이 문서는 `PEST_SCOUTING_STATE_DESIGN.md`의 상태 기반 예찰 정책을 실제 DB로 구현하기 위한 V1 schema 계약을 정의한다.

## 1. 목표

응애/병해충 예찰은 다음 요구를 동시에 만족해야 한다.

- 같은 구역의 과거 상태를 기억한다.
- 모든 관측은 이력으로 남긴다.
- 동일 패턴 반복 시 같은 알림을 매번 보내지 않는다.
- 새로운 변화가 생길 때만 재알림할 수 있다.
- 현장 사용자는 병명을 억지로 확정하지 않고 관찰 사실만 남길 수 있다.
- 현장 확인 결과는 영구 negative/positive 판정으로 과도하게 일반화하지 않는다.
- 향후 응애 이외 병해충/생리장해/환경 이상으로 확장 가능해야 한다.

## 2. 테이블 개요

```text
scouting_location_states      # 구역별 현재 상태 projection
scouting_cases                # 하나의 의심/발생 episode
scouting_observations         # 센서/영상/모델 관측 append-only
scouting_field_checks         # 작업자/농장주의 현장 evidence
scouting_actions              # 방제/제거/관찰 유지 등 조치
scouting_alert_events         # 발행/억제된 alert 이력
scouting_issue_catalog        # 응애/기타 병해충/환경 이상 taxonomy
```

기존 `mite_record_notes`는 migration audit 전까지 유지한다.

## 3. scouting_location_states

구역별 현재 상태를 빠르게 조회하는 projection 테이블이다.

```text
id
farm_id
location_key
house_code
bed_code
zone_code
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

### 제약

```text
UNIQUE(farm_id, location_key)
```

`location_key`는 derived key이며 source의 원본 `Farm`/`Zone`을 대체하지 않는다.

권장 state:

```text
BASELINE
WATCH
FIELD_CHECK_REQUIRED
SUSPECTED
CONFIRMED
POST_TREATMENT
MONITORING
RESOLVED
```

금지:

```text
NO_VISIBLE_EVIDENCE → VERIFIED_NEGATIVE 자동 변환
```

## 4. scouting_cases

하나의 연속된 의심/발생/조치 episode를 관리한다.

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
created_at
updated_at
```

권장 status:

```text
OPEN
MONITORING
POST_TREATMENT
RESOLVED
```

동일 위치에서 같은 상태가 반복됐다는 이유만으로 매일 새 case를 만들지 않는다.

새 case는 적어도 다음 중 하나가 충족될 때 생성 후보가 된다.

- 기존 case 없음 + meaningful anomaly 발생
- 기존 case 종료 후 충분한 시간 경과 뒤 새로운 anomaly 발생
- 기존 이슈와 질적으로 다른 새로운 issue family 발생

정확한 시간/거리 threshold는 field calibration 전 고정하지 않는다.

## 5. scouting_observations

모든 자동 관측을 append-only로 저장한다.

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

### source_type 예

```text
THERMAL
RGB_REFERENCE
SENSOR
MANUAL
FUSION
```

### 원칙

- observation은 alert가 억제되어도 저장한다.
- 원시/파생 feature는 provenance를 남긴다.
- 현재 state를 덮어쓰기 위한 유일한 source로 사용하지 않고 state service가 history를 해석한다.
- RGB는 V1에서 응애 객체 검출 필수 입력이 아니다.

## 6. scouting_field_checks

현장 작업자가 직접 관찰한 사실을 기록한다.

```text
id
farm_id
location_state_id
case_id nullable
observation_id nullable
checked_at
checker_member_id nullable
primary_evidence_code
secondary_evidence_json
note nullable
photo_asset_id nullable
created_at
```

### primary_evidence_code

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

### 핵심 의미

```text
NO_VISIBLE_EVIDENCE
= 점검 당시 뚜렷한 이상을 작업자가 확인하지 못함
≠ 응애가 존재하지 않음
```

```text
DIRECT_MITE_OR_EGG_CONFIRMED
= 확대 관찰 등으로 응애/알을 직접 확인한 강한 현장 evidence
```

`WEBBING_OR_MITE_TRACE_SUSPECTED`는 현재 활성 응애 확정과 동일하지 않다.

## 7. scouting_actions

현장에서 실제 수행한 조치를 기록한다.

```text
id
farm_id
location_state_id
case_id nullable
action_at
action_code
actor_member_id nullable
detail_json
note nullable
created_at
```

V1 action code 후보:

```text
TREATMENT_APPLIED
LEAF_REMOVED
BIOCONTROL_APPLIED
OBSERVE_ONLY
OTHER_ACTION
```

농민/작업자에게 상세 약제명/농도 입력을 기본 의무화하지 않는다.

## 8. scouting_alert_events

알림 발행 여부 자체도 이력으로 남긴다.

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

### alert_decision

```text
ISSUED
SUPPRESSED
ESCALATED
RECHECK_REQUESTED
```

### suppression_reason 예

```text
MATCHES_RECENT_KNOWN_PATTERN
NO_MEANINGFUL_NEW_EVIDENCE
RECENT_FIELD_CHECK_STILL_FRESH
ACTIVE_CASE_ALREADY_NOTIFIED
ENVIRONMENT_EXPLAINS_VARIATION
```

### re-alert reason 예

```text
NOVELTY_INCREASE
WORSENING_TREND
SPATIAL_SPREAD
NEW_FIELD_EVIDENCE
STALE_PREVIOUS_CHECK
POST_TREATMENT_REBOUND
```

정확한 cutoff 값은 schema에 하드코딩하지 않는다.

## 9. scouting_issue_catalog

응애 단일 기능으로 schema를 잠그지 않는다.

```text
code
family
display_name_ko
ai_capability
operational_status
created_at
updated_at
```

### family

```text
PEST
DISEASE
PHYSIOLOGICAL_ENVIRONMENTAL
UNKNOWN
```

### ai_capability

```text
SUPPORTED
ALERT_ONLY
RECORD_ONLY
```

예시:

```text
SPIDER_MITE / PEST / 응애 / ALERT_ONLY
UNKNOWN_PEST / PEST / 기타 해충 / RECORD_ONLY
UNKNOWN_DISEASE / DISEASE / 병해 의심 / RECORD_ONLY
ENVIRONMENTAL_STRESS / PHYSIOLOGICAL_ENVIRONMENTAL / 환경·생리 이상 / ALERT_ONLY
```

실제 검증 없이 `SUPPORTED`로 올리지 않는다.

## 10. 상태 전이 예시

### Case A — 동일 패턴 반복

```text
09/01
thermal anomaly
→ FIELD_CHECK_REQUIRED
→ field check = NO_VISIBLE_EVIDENCE
→ state = WATCH

09/02
동일한 thermal/environment pattern
→ observation append
→ alert_event = SUPPRESSED
→ state = WATCH 유지
```

### Case B — 새로운 악화

```text
09/05
novelty/trend/spatial signal 상승
→ alert_event = RECHECK_REQUESTED
→ state = FIELD_CHECK_REQUIRED
```

### Case C — 직접 확인

```text
field check = DIRECT_MITE_OR_EGG_CONFIRMED
→ case.primary_issue_code = SPIDER_MITE
→ state = CONFIRMED
```

### Case D — 방제 후 추적

```text
action = TREATMENT_APPLIED
→ state = POST_TREATMENT
→ 이후 observation 지속
→ signal 감소/안정 → MONITORING
→ policy 조건 충족 → RESOLVED
```

## 11. 기존 Health source와의 관계

현재 field source의 `Health`:

```text
NOR / MIT / MIT_R / ANT / MAL / OTH
```

은 **학습/원본 source label**이다.

운영 scouting state와 동일한 컬럼으로 합치지 않는다.

```text
Field source Health
→ immutable source/normalized label

Operational scouting state
→ live location state + history
```

예를 들어 과거 데이터에서 `Health=MIT`라고 되어 있어도 현재 운영 location state의 `CONFIRMED`를 자동 생성하지 않는다.

## 12. 기존 mite_record_notes migration 원칙

즉시 rename/delete 금지.

먼저 실제 사용처를 audit한다.

가능한 migration 방향:

```text
mite_record_notes
→ scouting case/observation에 연결되는 free-form note/evidence attachment
```

또는 실제 사용이 없다면 deprecation → migration → 제거를 별도 PR에서 수행한다.

## 13. Repository / Service 경계

Repository:

```text
state 조회/저장
observation append
case 조회/저장
field check append
action append
alert event append
```

Repository가 해서는 안 되는 것:

```text
응애 위험 판단
새 변화 판정
재알림 여부 결정
case open/close business rule 결정
```

Service/Policy:

```text
ScoutingStateService
ScoutingObservationService
ScoutingCaseService
ScoutingAlertService
RiskAggregationStrategy
NoveltyDetectionStrategy
AlertSuppressionPolicy
RealertPolicy
FieldEvidencePolicy
```

## 14. V1 구현 순서

```text
1. 현재 db/schema.ts와 mite_record_notes 사용처 audit
2. migration 파일 설계
3. issue catalog seed
4. append-only observation repository
5. location state projection
6. state transition tests
7. suppression/re-alert tests
8. field check API
9. action API
10. Farmer/Worker 최소입력 UI
11. 농장주 location history UI
12. field calibration
```

## 15. Acceptance

다음이 만족되어야 V1 scouting schema 구현 완료로 본다.

- 동일 구역의 observation history가 유지됨
- 현재 state와 history가 분리됨
- 반복 동일 observation을 저장하면서 alert만 suppress 가능
- field check 결과를 negative ground truth로 강제 변환하지 않음
- 새로운 변화 발생 시 재알림 가능
- treatment 이후 monitoring/rebound 추적 가능
- 응애 외 issue family로 확장 가능
- 기존 field Health 원본 의미를 훼손하지 않음
- 기존 mite_record_notes migration 전 raw history 손실 없음
