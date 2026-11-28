# 현장 확인 상위 선택 — 격리 후보

## PRECHECK / 선정 근거

- PROJECT_SCOPE MUST: 선택적인 현장 확인 및 UNKNOWN 보존, 농민이 이해할 상태→이유→행동.
- PEST_SCOUTING_UI_V1_CONTRACT §5와 §9: 상위 선택 이후 legacy evidence mapper 위에 generic finding UI를 추가한다. 조합 후보는 상세 안에8개 evidence 버튼을 바로 나열하므로 이 단계는 미구현이다.
- 이번 구현은4개 상위 선택과 기존8개 코드 연결만 담당한다. 기존 API에는 secondaryEvidence unknown JSON 필드가 있으나 종별/복수 finding의 typed domain·검증 계약은 아직 구현돼 있지 않다. 이를 임의로 새 의미의 저장 계약으로 사용하지 않는다. 배분50:50은 프로젝트 운영 방침이지 제품 입력 계약이 아니다.
- Single writer: root. 기존 후보·사용자 파일은 불변으로 두고 `/workspace/scratch/nongtori-finding-picker-J8KP1X` 사본만 변경한다. 기반은 조합105개 검사 후보이며 parent의2026-11-04 22:10UTC main3547c552 identical 근거 이후 원격 상태는 미확인이다.

## 수용 기준 / Product Flow

1. 상세의 선택적 현장 확인을 열기 전 추가 입력 요구 없음.
2. 4개 상위 선택에는 기본값이 없다. 상위 선택 자체로 POST/저장이 발생하지 않는다.
3. 상위 선택 후 해당하는 기존 결과 버튼을 명시적으로 눌러 기록한다. 기존8개 코드가 누락·중복되지 않는다. '이상 못 찾음'은 기존 관찰 evidence이고 음성/정상 진단으로 변경하지 않는다.
4. 기존 canReview/sending 경계를 유지한다. 농장·구역 변경 시 이전 선택은 노출하지 않는다. 입력 내용의 영구 저장·자동 POST·새 retry/key 동작은 추가하지 않는다.
5. 판정 코드는 기존 submitFieldCheck → 기존 API/권한/도메인으로 전달된다. 최근 입력 정정 패널·조치·종료·이력은 변경하지 않는다.
6.4개 언어와 기존44px touch/CSS token을 재사용한다. 실제 브라우저 검증은 접근 제한으로 NOT_RUN이며 합성 callback/markup을 시각 수용 PASS로 부르지 않는다.

## 검증 상태

```sh
node --import ./tests/register.mjs --test tests/scouting-finding-picker.test.tsx
node --import ./tests/register.mjs --test tests/scouting-finding-picker.test.tsx tests/scouting-ui.test.tsx
npm run test:workflows
./node_modules/.bin/tsc --noEmit --incremental false
npm run lint
npm run build
```

- 신규 표적5/5, 관련UI19/19, 실제 workflow110/110 PASS. 신규5개는4group의 기본값/비저장,8code 일대일 매핑, disabled/농장·구역변경,4언어와 선택중 fetch금지, 각code의 실제POST→권한→repository 저장/타농장403, Queue callback/key/권한연결을 검증한다. fresh synthetic binding만 사용하며 keyed 경로의 feature opt-in은 fixture에만 있다. 제품 기본 비활성 설정은 변경하지 않았다. 합성 picker callback 검사와 별도의 실제 POST 검사를 연결된 브라우저 UI→API E2E로 표현하지 않는다.
- 최종 TypeScript/lint/build PASS. 최초 TypeScript에서 테스트 변수 beforeSelection 추론의 TS7022 한 건을 확인하여 명시적 number 타입을 추가했다. any/검사억제/런타임 변경 없음. 해당 타입 표기는 transpile에서 제거되므로 기존 실행 결과의 의미가 바뀌지 않는다.
- 신규 파일은 presentation 책임만 담당하며 Controller/Service/Repository를 추가하거나 변경하지 않았다. 부모 상세가 기존farm/location key로 picker를 마운트한다. 기존8code label은 Queue에서 전달해 중복 도메인 라벨을 만들지 않는다.
- 실제 브라우저/mobile/focus/스크린리더/overflow, 실제 로그인·운영 D1은 NOT_RUN. 단순 상태 hook과 실제 callback 검사는 React DOM reconciliation을 증명하지 않는다. 기존 접근 거부를 재시도하거나 다른 경로로 우회하지 않았다. 실제 계정·운영 DB·실데이터·외부 서비스·브라우저·원격 게시·병합·배포는 제외했다.
- 독립 읽기 검수에서 새 P1/P2 없음. 검사 경계와 secondaryEvidence의 미완료 typed 계약을 명확히 하라는 문서 권고를 반영했다. Advisor 전용 설치 실행 경로는 없어 상담은 unavailable이며 독립 코드 검수와 구분한다.

## 다음 범위

현재 상태는 IMPLEMENTED / READY_FOR_WORK_QA인 로컬 후보다. 다른 후보들과 구간별로 분리해 게시 승인 대상으로 검수할 수 있으나 이번 요청에서는 게시하지 않는다. 아직 API가 정의하지 않은 종별/복수 finding, 환경 조정 action code, 과거입력 시간 정책은 임의 추가하지 않는다. 실제 브라우저 수용은 접근 가능한 공식 경로와 해당 승인이 있을 때 별도 진행해야 한다.
