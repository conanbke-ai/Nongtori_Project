# Nongtori Pest Scouting UI V1 Contract

Status: **CANONICAL UI CONTRACT — 2026-09-17**

## 1. 목적

병해충 예찰 화면은 농민/작업자에게 새로운 기록 업무를 강제하는 화면이 아니라, **어디를 먼저 확인할지 자동으로 좁혀주는 운영 화면**이다.

V1은 다음 흐름을 고정한다.

```text
병해충 관리
→ 의심구역 목록
→ 구역/CASE 상세
→ 필요 시 현장 확인 결과 기록
→ 필요 시 조치 기록
→ 이력 유지
```

사람 입력이 없어도 자동 관측/CASE monitoring은 계속된다.

## 2. 목록 화면

### 역할

- 확인 우선순위 파악
- 위치 파악
- 탐지 후보 파악
- 핵심 관측값 파악

목록 행에서 현장확인/조치 선택지를 모두 펼치지 않는다.

### 권장 컬럼

```text
위치 | 탐지 후보 | 상태 | 주요 신호 | 최근 감지
```

예:

```text
C2-37-E | 응애 | 확인 필요 | 습도 43% · 잎 온도 +1.8℃ | 오늘 14:20
```

### 위치

`house · bed · zone` 고정 조합을 화면 계약으로 사용하지 않는다.

API가 제공하는 다음 값을 우선한다.

```text
displayLocationCode
```

legacy runtime에서는 `location_key` 또는 기존 house/bed/zone을 adapter가 display code로 조합할 수 있다.

### 상태 문구

workflow state와 병해충 종류를 분리한다.

```text
FIELD_CHECK_REQUIRED → 확인 필요
SUSPECTED            → 이상 확인
CONFIRMED            → 확인 완료
WATCH                → 관찰 중
POST_TREATMENT       → 조치 후 관찰
MONITORING           → 추적 관찰
```

`CONFIRMED → 응애 확인`처럼 상태명 자체에 병해충명을 하드코딩하지 않는다.

실제 대상은 별도 표시한다.

```text
탐지 후보: 응애
```

## 3. 주요 신호 문구

농민 화면에서는 모델 내부 용어가 아니라 측정 가능한 사실을 보여준다.

우선 표현:

```text
습도 낮음       43%
잎 온도 상승    주변보다 +1.8℃
반복 감지       3회
```

또는 목록 compact 표현:

```text
습도 43% · 잎 온도 +1.8℃ · 3회 반복
```

피해야 할 기본 표현:

```text
열화상 이상 높음
thermal anomaly high
비선형 위험신호 증가
최근 건조 환경 지속   # 실제 수치 없이 추상 설명만 있는 경우
습도 관리 실패        # 관리 실패/인과 단정
```

VPD는 내부 판단에 사용할 수 있으나 기본 목록에서는 농민이 바로 이해하기 쉬운 값이 우선이다.

## 4. 상세 화면

목록 행 전체를 누르면 상세로 이동하거나 모바일에서는 full-screen/detail sheet를 연다.

상세 기본 구성:

```text
C2-37-E
상태: 확인 필요
탐지 후보: 응애

주요 정보
- 습도 43%
- 주변 대비 잎 온도 +1.8℃
- 반복 감지 3회

위치
- 농가에서 사용하는 실제 display path

최근 이력
- 09/17 확인 필요
- 09/14 관찰
- 09/10 최초 감지

[현장 확인 결과 기록]
[조치 기록]
[전체 이력]
```

raw thermal feature, VPD, 모델 버전, confidence 등은 상세의 보조/확장 영역으로 둔다.

## 5. 현장 확인 UX

현장 확인은 선택사항이다.

사용자가 상세에서 `현장 확인 결과 기록`을 눌렀을 때만 입력 UI를 보여준다.

상위 선택:

```text
이상 없음/뚜렷한 이상 못 찾음
병해충 발견
기타 이상 발견
판단 어려움
```

`병해충 발견` 선택 시에만 issue 선택 UI를 연다.

```text
추천
- 응애  # 현재 모델 후보

다른 병해충
- 총채벌레
- 진딧물
- 흰가루병
- 잿빛곰팡이병
- 기타
- 정확히 모르겠음
```

복수 finding을 허용한다.

현장 확인 저장 직후 `조치하셨나요?`를 강제 팝업으로 띄우지 않는다.

## 6. 조치 UX

조치는 별도 액션이다.

```text
조치 기록 없음
[조치 기록]
```

조치 후보:

```text
방제
피해잎 제거
천적 처리
환경 조정
추적 관찰
기타 조치
```

조치 기록이 없다는 것은 `미조치`가 아니다.

조치 후 CASE는 자동 종료하지 않고 `POST_TREATMENT` 또는 `MONITORING`으로 이어질 수 있다.

## 7. 입력 시점

현장 작업자가 현장에서 앱을 계속 조작한다고 가정하지 않는다.

```text
앱에서 위치 확인
→ 현장 이동
→ 실제 확인/작업
→ 나중에 앱 재진입
→ 결과/조치가 필요하면 기록
```

따라서 가능하면:

```text
observed_at / checked_at
recorded_at
```

을 분리한다.

V1 UI에서 정확한 시간을 강제 입력시키지 않는다. 기본 날짜/시간 자동값 + 필요 시 수정으로 충분하다.

## 8. 자동화 원칙

알림마다 담당자를 수동 배정하지 않는다.

```text
Detection N건
→ 동일 위치/CASE 병합
→ 반복 알림 억제
→ 우선순위화
→ 목록 표시
```

작업자 자동배정, workload balancing, 로봇 waypoint, 자동방제는 FUTURE다.

## 9. 현재 runtime gap

현재 `ScoutingQueue.tsx`는 다음 legacy UX를 포함한다.

- location 표시가 `house_code · bed_code · zone_code`에 고정
- `CONFIRMED` 상태 문구가 `응애 확인`으로 하드코딩
- 목록 카드 안에서 field check/action/resolve `<details>`를 즉시 펼칠 수 있음
- 응애 특화 evidence option이 직접 노출됨

이는 기존 기능 보존을 위해 즉시 삭제하지 않되, V1 UI 구현 시 다음 순서로 교정한다.

```text
1. list row는 summary-only로 축소
2. displayLocationCode adapter 도입
3. state label과 issue label 분리
4. 상세 화면/패널로 field check/action 이동
5. generic finding UI를 legacy evidence mapper 위에 추가
```

## 10. V1 Acceptance

- 목록에서 사용자가 3초 안에 확인 우선 위치를 파악할 수 있음
- 목록에 현장 입력폼이 기본 노출되지 않음
- 위치가 house 필수 구조를 요구하지 않음
- workflow 상태에 병해충명이 하드코딩되지 않음
- 주요 신호가 구체적 수치/관측 사실로 표현됨
- 현장 확인과 조치가 독립적 선택 액션임
- 아무 입력을 하지 않아도 CASE monitoring이 계속됨
- 모바일과 웹에서 동일 의미의 정보구조를 유지함
- 실제 브라우저 visual acceptance 전에는 UI 완료로 간주하지 않음
