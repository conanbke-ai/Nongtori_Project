# Pest Scouting UI Validation — 2026-09-17

Status: **PARTIAL PASS / ACTUAL APP BROWSER QA BLOCKED**

이 문서는 2026-09-17 병해충 예찰 V1 UX refreeze 후 수행한 검증과 미검증 범위를 기록한다.

## 1. 검증 대상

- `app/features/pests/presentation/ScoutingQueue.tsx`
- `app/features/pests/presentation/scouting.css`
- `app/api/scouting-locations/route.ts`
- `tests/scouting-ui.test.tsx`

관련 canonical:

- `docs/PEST_SCOUTING_STATE_DESIGN.md`
- `docs/PEST_SCOUTING_DB_SCHEMA_V1.md`
- `docs/PEST_SCOUTING_UI_V1_CONTRACT.md`
- `docs/MULTI_FARM_DATA_MODEL.md`

## 2. 확인된 구현 계약

### PASS — summary list → detail

- 목록 행은 위치 / workflow 상태 / 탐지 후보 / 핵심 자동 관측 신호 / 최근 감지를 요약한다.
- 현장확인·조치·종료 입력은 목록 행 안에 상시 노출하지 않고 선택된 상세 패널 안에 둔다.
- 데스크톱은 list/detail 2열, 좁은 화면에서는 1열로 전환하도록 CSS가 정의되어 있다.
- 주요 작업 버튼은 최소 44px hit area를 유지한다.

### PASS — workflow state / issue identity 분리

`CONFIRMED`는 화면에서 `현장 확인 완료`로 표현하며 `응애 확인`으로 하드코딩하지 않는다.
실제 탐지/확인 대상은 `primary_issue_code`를 통해 별도로 표시한다.

### PASS — farmer-facing concise evidence

가능한 경우 목록/상세에 다음과 같이 관측값을 직접 표시한다.

```text
습도 43%
잎 온도 +1.8℃
관측 3회
```

`thermal anomaly high`, `습도 관리 실패` 같은 개발자 용어/인과 단정은 기본 UI 문구로 사용하지 않는다.

### PASS — legacy location display compatibility

현재 runtime은 compatibility schema에서 `location_key`를 다음처럼 생성한다.

```text
C2:37:E
```

이를 그대로 사용자 화면에 노출하지 않도록 API projection에서 `:`를 `-`로 바꿔 다음처럼 표시한다.

```text
C2-37-E
```

DB identity 자체는 변경하지 않는다. 이는 향후 `spatial_unit_id + display_code` 전환 전까지의 compatibility projection이다.

대표 SQLite 재현 검증:

```text
source location_key      = C2:37:E
display_location         = C2-37-E
latest humidity          = 43
latest leaf temp         = 26.2
latest ambient temp      = 24.4
active-case observations = 2
```

## 3. 정적/구문 검증

확인 완료:

- `ScoutingQueue.tsx` TypeScript/TSX transpile syntax diagnostics: `0`
- `scouting-locations/route.ts` TypeScript syntax diagnostics: `0`
- 대표 SQLite schema에서 scouting location projection query parse/execute 성공
- UI source regression assertions 확인:
  - `CONFIRMED != 응애 확인` 하드코딩
  - `SPIDER_MITE -> 응애` 별도 identity
  - summary row / detail panel 존재
  - humidity / leaf-temperature metric 표현
  - `응애 아님` 자동 negative 문구 없음

## 4. 이번 환경에서 실행하지 못한 검증

### BLOCKED — full repository workflow / lint / build

현재 실행 컨테이너에서 GitHub host DNS/network 접근이 차단되어 repository clone 및 npm dependency install을 수행할 수 없었다.

또한 현재 repository branch budget가 이미 full이며 unrelated branch를 삭제/재사용하지 않는 정책을 유지했다. App workflow는 PR trigger 중심이고 이 세션에서 workflow dispatch action은 사용할 수 없었다.

따라서 아래를 PASS로 주장하지 않는다.

```text
npm run test:workflows
npm run lint
npm run build
```

### BLOCKED — actual application browser/mobile visual acceptance

컨테이너에는 system Chromium이 있으나 actual application을 build/start할 dependency tree가 없으며 외부 dependency 설치가 불가능하다.
Playwright packaged browser도 설치되어 있지 않다. system Chromium을 통한 제한적 headless 실행은 가능했지만 actual Nongtori runtime을 띄울 수 없으므로 실제 앱 visual acceptance로 인정하지 않는다.

따라서 다음은 **미완료**다.

- actual Nongtori route 렌더링
- real farm/session payload 기반 list/detail interaction
- desktop/mobile screenshot acceptance
- field-check/action interaction browser test

## 5. 현재 판정

```text
Design / contract          PASS
TS/TSX syntax              PASS
API SQL projection         PASS
Legacy display projection  PASS
Source regression guards   PASS
Full workflow test         BLOCKED / NOT CLAIMED
Lint / build               BLOCKED / NOT CLAIMED
Actual browser visual QA   BLOCKED / NOT CLAIMED
```

현재 변경을 `visual acceptance complete` 또는 production-ready로 표현하지 않는다.
