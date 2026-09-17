# Nongtori Pest Scouting State Design

Status: **CANONICAL / V1 SCOPE & UX REFREEZE — 2026-09-17**

이 문서는 농토리의 병해충 예찰을 특정 병해충의 단발성 분류가 아니라 **공간 단위 상태 이력 기반 예찰(stateful scouting)** 로 운영하기 위한 canonical 기준을 정의한다.

첫 자동 예찰 개발 대상은 응애지만, CASE·상태·현장확인·조치·UI는 응애에 종속시키지 않는다.

## 1. V1 제품 목표

V1의 목표는 `AI가 응애를 확정 진단하고 자동 방제하는 시스템`이 아니다.

```text
자동 관측
→ 위험/이상 신호 계산
→ 같은 공간의 기존 CASE와 병합
→ 확인 우선순위가 높은 구역만 목록화
→ 사용자는 필요할 때 상세 확인
→ 현장 확인/조치가 기록되면 선택적 evidence로 누적
→ 입력이 없어도 다음 자동 관측과 위험도 계산은 계속 수행
```

V1은 다음을 우선한다.

- Thermal / Environment 중심 자동 관측
- 동일 위치의 최근 관측과 비교 가능한 history 유지
- 불규칙 반복 관측의 시간 간격을 보존
- 반복 동일 경보 억제
- 사람이 확인해야 할 위치를 줄여서 제시
- 현장 입력을 inference 필수 dependency로 만들지 않음
- 향후 다른 병해충/질병으로 확장 가능한 taxonomy 유지

## 2. 실제 현장 데이터 전제

현재 field data는 규칙적인 일 단위 연속 시계열이 아니다.

- 주 관찰 농가는 수확 일정 등 현장 운영 때문에 촬영 위치/시설이 날짜마다 달라질 수 있음
- 같은 위치를 다른 날 다시 촬영한 데이터는 있으나 관측 간격이 불규칙함
- 외부 피해 농가는 피해구역/비피해구역을 한시적으로 비교 촬영한 단면(case/control) 데이터가 포함됨
- 과거 피해 흔적, 방제 이후 잔존 위험, 현재 활성 발생이 혼재할 수 있음
- 운영 중 농민/작업자가 현장 결과를 항상 입력한다고 가정할 수 없음

따라서 V1은 규칙적인 sequence를 강제하지 않는다.

```text
현재 관측
+ 이전 관측이 있으면 변화량/경과시간
+ 환경 맥락
+ 공간 맥락
→ 위험 CASE
```

장기 sequence model은 FUTURE 연구 후보이며 V1 완료 조건이 아니다.

## 3. 핵심 원칙

### 3.1 자동 수집 데이터만으로 항상 동작

Core inference는 사람이 입력하지 않아도 작동해야 한다.

```text
Thermal
+ Temperature / RH / VPD / available environment
+ timestamp
+ spatial context
+ automatically available history
→ Risk / Novelty / Trend / Spatial signals
```

현장확인/방제 입력은 선택적 evidence다.

### 3.2 미입력은 음성 라벨이 아니다

```text
UNVERIFIED != NORMAL
UNVERIFIED != NO_PEST
UNKNOWN_TREATMENT != NOT_TREATED
```

사람이 아무것도 입력하지 않았다는 이유로 정상/음성 ground truth를 생성하지 않는다.

### 3.3 관측은 저장하고 알림만 억제

```text
Observation append
→ State/Case 비교
→ Alert issue/suppress 판단
```

동일 패턴 반복이라도 observation history는 보존한다.

### 3.4 병해충 종류와 workflow 상태를 분리

상태는 업무/예찰 lifecycle을 뜻한다.

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

`CONFIRMED` 자체가 `응애 확인`을 뜻하지 않는다.
실제 확인 대상은 `issue_code` 또는 field finding으로 별도 저장한다.

예:

```text
state = CONFIRMED
primary_issue_code = SPIDER_MITE
```

향후에는 같은 상태 계약으로 `THRIPS`, `APHID`, `POWDERY_MILDEW` 등을 수용할 수 있다.

### 3.5 공간구조를 동/베드/구역으로 고정하지 않음

Canonical 위치 구조는 `MULTI_FARM_DATA_MODEL.md`의 가변 SpatialUnit hierarchy를 따른다.

```text
Farm
→ SpatialUnit
→ optional child SpatialUnit ...
→ 실제 관리/관측 단위
```

`HOUSE`는 선택 가능한 공간 타입이지 필수 단계가 아니다.

Logical location identity는 목표 구조에서 다음을 우선한다.

```text
farm_id + spatial_unit_id
```

기존 runtime의 `house/bed/zone`은 migration 전 compatibility field로 취급한다.

### 3.6 자동화는 사용자 클릭 수를 늘리면 안 됨

모델 detection마다 농장주가 담당자를 지정하거나 새 작업을 생성하게 하지 않는다.

V1 기본:

```text
Detection 여러 건
→ 같은 위치/CASE 자동 병합
→ 우선순위화
→ 병해충 관리 목록에 표시
```

작업자 자동배정/스케줄 최적화/로봇 waypoint는 FUTURE다.

## 4. 상태 의미

### BASELINE
평상 패턴 또는 유의미한 이상 신호 없음.

### WATCH
변화는 있으나 현장 확인 요청 수준은 아님.

### FIELD_CHECK_REQUIRED
새로운 이상, 악화, 반복/확산 등으로 현장 확인 가치가 높아진 상태.

### SUSPECTED
현장에서 병해충/병해/환경 이상 가능성을 시사하는 evidence가 관찰되었으나 대상이 확정되지 않았거나 강한 확증이 부족함.

### CONFIRMED
특정 issue가 현장 evidence로 확인됨. 대상은 `primary_issue_code`/finding으로 별도 저장.

### POST_TREATMENT
방제·제거 등 조치 기록이 있음. 조치 기록 자체가 해결을 뜻하지 않음.

### MONITORING
조치 또는 의심 이후 후속 관찰 중.

### RESOLVED
명시적인 종료 event가 발생한 CASE. 자동 방제 완료만으로 종료하지 않는다.

## 5. CASE와 Observation

`DetectionEvent/Observation`과 `RiskCase`를 분리한다.

같은 위치에서 세 번 감지되었다고 목록에 세 행을 만들지 않는다.

```text
CASE C2-37-E
├─ 09/10 observation
├─ 09/12 observation
└─ 09/16 observation
```

화면은 CASE 한 행을 보여주고 `반복 감지 3회`처럼 요약한다.

새 CASE는 최소 다음 상황에서 생성 후보가 된다.

- 해당 위치에 active CASE가 없는데 meaningful anomaly 발생
- RESOLVED 이후 새로운 meaningful anomaly 발생
- 기존 CASE와 질적으로 다른 issue family가 별도 관리되어야 함

## 6. Field Verification / Finding

현장 입력은 진단문 작성이 아니라 **관찰 사실을 짧게 남기는 기능**이다.

현장확인의 상위 결과는 범용으로 유지한다.

```text
NO_VISIBLE_ABNORMALITY
ISSUE_FOUND
OTHER_ABNORMALITY
INCONCLUSIVE
```

`ISSUE_FOUND`인 경우 구체 대상은 finding으로 분리한다.

```text
FieldFinding
- family: PEST | DISEASE | PHYSIOLOGICAL_ENVIRONMENTAL | UNKNOWN
- issue_code: optional
- certainty: optional
- severity: optional
```

한 현장 확인에 finding이 여러 개일 수 있다.

```text
SPIDER_MITE
+ POWDERY_MILDEW
```

현재 runtime의 mite-specific evidence code는 기존 이력 호환을 위해 보존할 수 있으나, 신규 UI/도메인 계약은 범용 finding 구조를 목표로 한다.

`특별한 이상을 못 찾음` 역시 강한 음성 ground truth로 자동 승격하지 않는다.

## 7. Action

현장확인과 조치를 강제로 한 흐름으로 묶지 않는다.

```text
확인 결과 기록
≠ 즉시 조치 입력 강제
```

조치가 있으면 별도 ActionEvent로 기록한다.

V1 표시 예:

```text
방제
피해잎 제거
천적 처리
환경 조정
추적 관찰
기타 조치
```

화면에서 기록이 없으면 `미조치`가 아니라 **조치 기록 없음**으로 표시한다.

## 8. Alert suppression / re-alert

### Suppression 후보

- 동일 active CASE의 최근 패턴과 실질적 차이가 없음
- 최근 관측 대비 의미 있는 novelty/trend/spread가 없음
- 이미 알림된 수준의 신호가 반복됨
- 환경조건 변화로 설명 가능한 변동이고 새로운 evidence가 없음

### Re-alert 후보

- 새로운 anomaly
- worsening trend
- 이상 범위 확대/인접 공간 확산
- 이전 확인 이후 새로운 evidence
- field-check freshness 저하
- post-treatment rebound

정확한 기간/임계값은 field calibration 전 임의 고정하지 않는다.

## 9. 화면 UX Freeze

### 9.1 목록의 역할

목록은 `어디를 먼저 볼지`만 빠르게 결정하게 한다.

기본 행 예:

```text
C2-37-E | 응애 후보 | 확인 필요 | 습도 43% · 잎 온도 +1.8℃ | 오늘 14:20
```

목록에 큰 입력폼이나 다수의 조치 버튼을 노출하지 않는다.
행 전체를 눌러 상세로 진입한다.

### 9.2 상세의 역할

상세는 `왜 확인해야 하는지`, `어디인지`, `최근에 어떻게 변했는지`를 보여준다.

농민 화면에서는 모델 내부 용어보다 관측 사실을 우선한다.

권장 표현:

```text
습도 낮음        43%
잎 온도 상승     주변보다 +1.8℃
반복 감지        3회
```

피해야 할 기본 표현:

```text
thermal anomaly high
비선형 위험신호 증가
최근 건조 환경 지속  # 구체 값 없이 추상 표현만 사용
습도 관리 실패      # 인과/책임 단정
```

VPD 등 전문 수치는 상세/보조 정보로 제공할 수 있다.

### 9.3 현장 확인은 선택적

상세 화면에는 다음 액션을 제공할 수 있다.

```text
[현장 확인 결과 기록]
[조치 기록]
[이력 보기]
```

현장에서 즉시 입력할 것을 전제로 하지 않는다.
사용자는 현장 확인 후 나중에 앱을 열어 기록할 수 있으며, 아무 입력을 하지 않아도 CASE monitoring은 계속된다.

### 9.4 담당자 수동 배정은 V1 기본 흐름에서 제외

알림마다 농장주가 담당자를 지정하도록 요구하지 않는다.
대규모 농가의 자동 routing/task scheduling은 Future architecture로만 열어둔다.

## 10. 모델/데이터 사용 범위

현재 데이터로 바로 주장하지 않는다.

- 열화상 단독 응애 확정 진단
- 규칙적인 장기 시계열 조기예측 성능
- 모든 병해충 자동분류
- 저습도와 응애 발생의 단일 인과관계

현재 검증 가능한 방향:

```text
Thermal + Environment risk signal
현재 관측 + 불규칙 이전 관측 변화량
다농가/공간 holdout
외부 피해농가 case/control retrospective audit
운영 CASE의 alert burden / field evidence 분석
```

## 11. V1 / SHOULD / FUTURE

### MUST

- stateful CASE/history
- 병해충 공통 taxonomy
- 응애 첫 자동 예찰 Strategy
- 자동 CASE 병합/반복 알림 억제
- 목록 → 상세 UX
- 구체적 환경/열화상 근거 표시
- 선택적 field verification/action
- UNKNOWN 보존
- 가변 SpatialUnit 계약

### SHOULD

- 이전 관측 대비 변화량과 `Δt`
- VPD/습도 지속시간 등 temporal feature
- post-treatment rebound 시각화
- farm/spatial holdout validation

### FUTURE

- 병해충 전체 AI 자동판별
- 작업자 자동배정/스케줄 최적화
- 로봇 재촬영 경로 자동삽입
- 자동 방제/처방
- 장기 sequence deep model

## 12. Freeze

- 사람 입력은 inference 필수 dependency가 아니다.
- 미입력은 정상/음성 라벨이 아니다.
- 상태 enum과 병해충 종류를 분리한다.
- CASE는 observation과 분리한다.
- 공간구조를 `house → bed → zone`으로 고정하지 않는다.
- 응애는 첫 Strategy일 뿐 병해충 관리 domain 전체를 응애 전용으로 만들지 않는다.
- 목록은 확인 위치 선택, 상세는 근거/이력/선택 입력 책임을 가진다.
- 알림마다 수동 담당자 배정을 V1 기본 흐름으로 넣지 않는다.
- Future 확장성을 이유로 V1 구현 완료를 지연시키지 않는다.
