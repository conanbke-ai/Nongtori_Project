# Nongtori Pest Scouting State Design

Status: **CANONICAL CANDIDATE / DESIGN FREEZE EXTENSION**

이 문서는 농토리의 병해충/응애 예찰을 단발성 분류가 아니라 **구역별 상태 이력 기반 예찰(stateful scouting)** 로 운영하기 위한 기준을 정의한다.

## 1. 제품 목표

농토리 V1의 응애 기능은 `응애 객체를 RGB에서 직접 찾는 모델`을 전제로 하지 않는다.

현재 현장 데이터에는 다음 한계가 있다.

- RGB는 열화상 대조용 성격이 강하고 응애 개체 식별용 고해상도 촬영이 아님
- 이미 응애 피해가 있었던 곳과 현재 응애가 존재할 수 있는 곳이 혼재함
- 소량의 거미줄/피해 흔적이 과거 피해인지 현재 활성 발생인지 단일 이미지에서 확정하기 어려움
- `정상 → 초기 유입 → 초기 피해 → 확산`을 동일 위치에서 연속 추적한 longitudinal ground truth가 부족함

따라서 V1 목표는 다음과 같다.

```text
구역별 평상/최근 상태 기억
+ Thermal / Environment / optional RGB evidence 누적
+ 이전 검증 상태와 비교한 새로운 변화 감지
+ 불필요한 반복 알림 억제
+ 필요한 구역만 현장 점검 요청
+ 점검/조치 결과를 다시 이력에 반영
```

농토리는 초기부터 `응애 확정`을 자동 선언하지 않는다. 운영 데이터가 충분히 축적되고 현장 검증을 거친 이후에만 더 강한 위험/방제 권고 단계로 확장한다.

## 2. 핵심 원칙

### 2.1 관측은 항상 저장하고 알림만 억제한다

같은 상태가 반복된다고 데이터를 버리지 않는다.

```text
Observation 저장
→ State 비교
→ Alert 필요성 판단
```

알림이 억제되어도 observation history에는 남긴다.

### 2.2 `특별한 이상을 못 찾음`은 `응애 없음`이 아니다

현장 점검에서 응애를 육안으로 못 봤다는 사실만으로 negative ground truth를 만들지 않는다.

```text
NO_VISIBLE_EVIDENCE != MITE_NEGATIVE
```

응애는 크기가 작고 잎 뒷면/미세 피해 단계에서 즉시 육안 확정이 어려울 수 있으므로 현장 입력은 **진단값보다 관찰 사실(evidence)** 중심으로 저장한다.

### 2.3 동일 수치 반복보다 `새로운 변화`를 본다

예:

```text
09/01 C2-23-G
ΔT = +3.2
→ FIELD_CHECK_REQUIRED
→ 현장: NO_VISIBLE_EVIDENCE

09/02 C2-23-G
ΔT = +3.2
환경조건/열 패턴도 유사
→ Observation 저장
→ Alert SUPPRESSED

09/05 C2-23-G
ΔT 증가 또는 이상 영역 확대/지속/인접 확산
→ NEW_EVIDENCE
→ FIELD_CHECK_REQUIRED 재발행
```

`Leaf_Temp - Amb_Temp > 임의 고정값` 하나로 매번 동일 알림을 생성하지 않는다.

### 2.4 구역별 baseline을 유지한다

농가/동/베드/구역마다 일사, 통풍, 수분 조건이 다를 수 있으므로 전 농장 공통 고정 임계값만으로 상태를 판단하지 않는다.

최소 logical key:

```text
farm_id + house + bed + zone
```

원본 `Farm`/`Zone`은 source 그대로 보존하고 derived location은 내부 식별자로 관리한다.

### 2.5 현재 상태와 이력은 분리한다

- 현재 상태: 빠른 조회/알림 판단용 materialized state
- 이력: append-only observation/case/check/action event

현재 상태를 수정하더라도 과거 관측/판단/현장 입력을 덮어쓰지 않는다.

## 3. 상태 모델

V1 권장 상태:

```text
BASELINE
  정상/평상 패턴 또는 아직 유의미한 이상 없음

WATCH
  이상 신호는 있으나 재확인 요청 수준은 아님

FIELD_CHECK_REQUIRED
  최근 검증 상태와 비교해 새롭거나 악화된 변화가 있음

SUSPECTED
  현장에서 피해 흔적/거미줄 등 응애 관련 evidence가 관찰됨
  단, 응애/알 자체를 확정한 것은 아님

CONFIRMED
  확대 관찰 등으로 응애/알을 직접 확인한 강한 evidence

POST_TREATMENT
  방제/제거 등 조치가 기록됨

MONITORING
  조치 이후 또는 의심 이후 추적 관찰 중

RESOLVED
  일정 기간 새로운 악화 신호가 없고 현장 운영정책상 사건 종료
```

`VERIFIED_NEGATIVE`를 핵심 상태로 사용하지 않는다. 현장 미관찰은 false negative 가능성이 있기 때문이다.

## 4. 개념 데이터 모델

실제 DB 구현 시 naming은 migration 검토 후 확정하되 책임은 아래처럼 분리한다.

### 4.1 `scouting_location_state`

구역별 현재 상태를 유지한다.

주요 필드 후보:

```text
location_key
farm_id
house
bed
zone
current_state
active_case_id
last_observed_at
last_field_check_at
last_action_at
last_alert_at
last_alert_reason
baseline_version
recent_pattern_fingerprint
updated_at
```

이 테이블은 history source of truth가 아니라 현재 상태 projection이다.

### 4.2 `scouting_observations`

센서/영상/모델 관측을 append-only로 저장한다.

주요 필드 후보:

```text
id
location_key
observed_at
capture_session_id
source_asset/frame reference
leaf_temp
ambient_temp
reference_temp
humidity
light_level
thermal_features_json
rgb_reference_json
model_version
risk_signal
novelty_signal
trend_signal
spatial_signal
alert_decision
alert_reason
created_at
```

RGB는 V1에서 응애 객체 검출을 보장하는 필수 modality가 아니다. 사용 시 reference/evidence 보조 역할로 취급하고 실제 validation으로 기여도가 확인될 때만 자동 판단 feature로 승격한다.

### 4.3 `scouting_cases`

하나의 발생/의심 episode를 관리한다.

```text
id
location_key
issue_family
opened_at
current_status
opened_reason
closed_at
close_reason
```

동일 상태 반복 관측만으로 case를 매번 새로 만들지 않는다.

### 4.4 `scouting_field_checks`

작업자/농장주의 현장 관찰 사실을 기록한다.

V1 evidence code 후보:

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

필수 원칙:

- `NO_VISIBLE_EVIDENCE`를 `MITE_NEGATIVE`로 변환하지 않음
- 사용자가 세부 병명을 모르면 강제로 선택시키지 않음
- 상세 병해충 분류는 선택사항이며 unknown 상태를 허용
- 현장 입력 횟수/필드를 최소화함

### 4.5 `scouting_actions`

방제/제거/관찰 유지 등 조치를 기록한다.

예:

```text
TREATMENT_APPLIED
LEAF_REMOVED
BIOCONTROL_APPLIED
OBSERVE_ONLY
OTHER_ACTION
```

V1에서 약제 종류/농도/전문 처방 입력을 필수화하지 않는다. 필요한 운영 범위에서만 확장한다.

### 4.6 issue taxonomy

운영 DB는 응애 하나에 고정하지 않는다.

최소 상위 분류:

```text
PEST
DISEASE
PHYSIOLOGICAL_ENVIRONMENTAL
UNKNOWN
```

V1 자동 inference capability는 응애/열 이상 등 실제 검증된 항목에만 선언한다. 나머지는 `RECORD_ONLY` 또는 수동 evidence로 남길 수 있다.

## 5. Alert suppression / re-alert 정책

### 5.1 Suppression

다음 조건은 **새로운 관측은 저장하되 반복 알림을 억제**하는 근거가 될 수 있다.

- 최근 field check 이후 상태/패턴 변화가 유의미하지 않음
- 현재 observation이 최근 verified/observed baseline과 매우 유사함
- 동일 case에서 같은 수준의 watch signal이 반복됨
- 환경조건 변화로 설명 가능한 변동이며 새로운 악화 evidence가 없음

정확한 거리/유사도/시간 threshold는 현재 임의 숫자로 freeze하지 않는다. field calibration 결과로 versioned policy를 만든다.

### 5.2 Re-alert

다음은 재알림 후보다.

- 최근 상태 대비 novelty 증가
- thermal anomaly의 지속적 악화 추세
- 이상 영역 확대
- 인접 zone으로 spatial spread
- 환경조건을 고려해도 설명되지 않는 변화
- 새로운 현장 evidence 발생
- 이전 현장 점검의 freshness가 충분히 낮아져 재확인이 필요한 경우
- 방제 후 다시 악화되는 rebound signal

### 5.3 Staleness

과거 field check 결과는 영구 suppression 근거가 아니다.

```text
last_field_check_at
+ policy-defined freshness
```

로 관리하며 freshness는 농가/시즌/운영 데이터에 따라 조정 가능한 정책값으로 둔다.

## 6. Decision flow

```text
New Observation
      ↓
Location State 조회
      ↓
환경 보정 + 최근 history 비교
      ↓
Risk / Novelty / Trend / Spatial signal 생성
      ↓
기존 case / field check / treatment history 결합
      ↓
┌──────────────────────────────────┐
│ same known pattern / no new info │ → SAVE + SUPPRESS
└──────────────────────────────────┘
                  │
                  └─ meaningful new change
                           ↓
                  FIELD_CHECK_REQUIRED
                           ↓
                     Field Evidence
                           ↓
          state/case 업데이트 + history append
```

## 7. Human verification의 역할

현장 확인은 농토리의 영구 필수 절차가 아니라 **초기 신뢰 형성 및 ground truth 축적 수단**이다.

단계적 운영 목표:

```text
Phase 1 — Validation-heavy
알림 → 현장 점검을 자주 요청

Phase 2 — Trust building
반복적으로 검증된 패턴은 확인 빈도 감소

Phase 3 — Operational trust
충분히 검증된 고위험 패턴에는 강한 위험/방제 검토 알림 제공

Future
농가 정책과 현장 검증 수준이 충분한 경우 일부 패턴은 즉시 대응 근거로 활용 가능
```

`CONFIRMED` 또는 높은 위험 신호만으로 자동 약제 살포를 기본 동작으로 만들지 않는다. 자동 제어는 별도 safety/robot policy가 필요하다.

## 8. 제품 UX 원칙

### 8.1 Farmer/Worker 입력 최소화

농민/작업자가 기록 문서를 작성하게 하지 않는다.

```text
농토리가 자동 기록
→ 사용자는 관찰 사실/조치만 짧게 선택
```

V1 현장 점검 예:

```text
[특별한 이상 못 찾음]
[잎 피해 흔적 있음]
[거미줄/응애 흔적 의심]
[응애/알 직접 확인]
[다른 이상]
[판단 어려움]
```

### 8.2 농장주 화면

전체 raw metric보다 **오늘 확인할 위치와 변화 이유**를 우선한다.

예:

```text
C2동 · 23번 베드 · G구역
상태: 다시 확인 필요
이유:
- 최근 기준보다 열 이상 증가
- 동일 구역 3회 연속 악화
- 최근 현장 점검 이후 새로운 변화
```

세부 화면에서만 원시 온도/습도/광량/모델 정보와 이력을 제공한다.

### 8.3 Alert fatigue 방지

제품 KPI에서 단순 detection accuracy만 보지 않는다.

운영 metric 후보:

- 불필요한 재알림 비율
- 동일 case 내 중복 alert 수
- alert → field check 비율
- alert → action 비율
- 실제 발생/현장 evidence보다 얼마나 선행했는지
- false-alert burden
- zone당 일/주 확인 요청 빈도
- treatment 이후 signal 감소/재발 여부

## 9. 현재 데이터에 대한 사용 범위

현재 field data로 바로 주장하면 안 되는 것:

- 피해 전 응애 조기예측 성능 확정
- RGB 기반 응애 객체 검출 성능 확정
- 열화상 단독 `응애 있음/없음` 확정
- 과거 피해 흔적과 현재 활성 응애를 완벽하게 분리

현재 가능한 연구 방향:

```text
Thermal anomaly baseline
Thermal + Environment 비교
optional RGB auxiliary contribution 검증
구역/세션/현장 라벨 기반 retrospective audit
```

운영 데이터가 쌓이면 다음 longitudinal evidence를 확보한다.

```text
alert
→ 현장 evidence
→ 이후 변화
→ 방제 여부
→ 회복/악화
```

이 데이터가 V2/V3 조기예찰 모델의 핵심 ground truth가 된다.

## 10. 모델 단계

```text
V1
이미 존재하는 이상/응애 피해 연관 위험 구역 선별
+ state/history 기반 재알림 제어

V2
초기 피해/약한 변화 탐지
+ 농가/구역별 baseline calibration

V3
육안 피해가 명확해지기 전 선행 위험 신호 연구
+ longitudinal field validation
```

V3는 모델 튜닝만으로 달성할 수 없다. 동일 위치의 정상→발생 전후 시계열 ground truth가 필요하다.

## 11. 구현 경계

권장 Domain 후보:

```text
ScoutingLocationState
ScoutingObservation
ScoutingCase
FieldCheckEvidence
ScoutingAction
ScoutingAlertDecision
ScoutingPolicy
```

권장 Service:

```text
ScoutingObservationService
ScoutingStateService
ScoutingAlertService
ScoutingCaseService
```

권장 Strategy/Policy:

```text
RiskAggregationStrategy
NoveltyDetectionStrategy
AlertSuppressionPolicy
RealertPolicy
FieldEvidencePolicy
```

Repository는 저장/조회만 담당하며 `응애 의심`, `새로운 변화`, `재알림 필요` 판단을 하지 않는다.

## 12. Freeze 사항

V1에서 다음을 freeze한다.

- 병해충 예찰은 stateless threshold alert가 아니라 location-state/history 기반으로 판단
- observation은 append-only history로 저장
- current state는 history와 분리된 projection
- 반복 동일 observation은 저장하되 alert suppression 가능
- 현장 미관찰을 자동 negative ground truth로 변환 금지
- alert suppression은 영구 면제가 아니며 freshness/staleness를 가짐
- RGB 응애 객체 탐지를 V1 전제조건으로 두지 않음
- Thermal anomaly를 응애 확정값으로 해석하지 않음
- 농민/작업자에게 상세 병명 입력을 기본 요구하지 않음
- 응애 이외 병해충/환경 이상으로 확장 가능한 taxonomy 유지
- human verification은 현재 validation evidence이며 영구 필수 절차로 고정하지 않음
- threshold/기간/위험점수 숫자는 field calibration 전 임의 freeze 금지

## 13. Design Review 재오픈 조건

다음 변경은 design review가 필요하다.

- 구역별 state/history를 제거하고 stateless alert로 회귀
- `NO_VISIBLE_EVIDENCE`를 자동 `MITE_NEGATIVE`로 처리
- field check 없이 기존 observation을 삭제/덮어쓰기
- 과거 점검 결과로 영구 alert suppression
- thermal anomaly를 직접 응애 확정 label로 변경
- 자동 방제/약제 살포를 기본 동작으로 추가
- issue taxonomy를 응애 단일 타입으로 축소

## 14. 다음 구현 순서

```text
1. 기존 db/schema 및 mite_record_notes 영향도 audit
2. conceptual table → concrete schema/migration 설계
3. state transition unit test 작성
4. alert suppression/re-alert policy test fixture 작성
5. 기존 field Health/MIT/MIT_R source와 운영 scouting state의 mapping 분리
6. API DTO
7. Farmer/Worker 최소입력 UI
8. 농장주 zone status/history UI
9. 실 field calibration
```

기존 `mite_record_notes`는 즉시 삭제하지 않는다. 실제 사용처와 migration 영향을 먼저 확인하고, 필요하면 새 scouting 모델의 note/evidence relation으로 점진적으로 연결한다.
