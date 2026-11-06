# 조회 범위 밖 정정 원본 — 로컬 후보

## 근거와 수용 기준

PROJECT_SCOPE V1의 CASE/history 및 기존 선택 구역 이력 후보를 잇는다. 최근50건에서 빠진 원본은 기존 이력 읽기 권한 안에서 별도 조회한다. 기존 GET history의 ACTIVE 구성원/viewHistory 계약과 원본 보존 의미를 유지한다. 작성자 전용이나 관리자 cross-farm 권한을 새로 만들지 않는다.

PRECHECK 범위: 기존8파일 후보에 단건 action이 없음을 확인한 뒤 별도 사본에 구현했다. 원본·사진 후보·기존 staged 내용은 수정하지 않는다. 새 경로는 Controller → read Service → Repository이며 bootstrap/DDL/업무 쓰기를 호출하지 않아야 한다. 실제 DB·계정·외부 호출·브라우저 제한 우회·게시·배포는 제외한다.

Product flow: 구역 선택 → 이력 명시 조회 → 최근50건 밖 정정 원본 버튼 → 조회 중 → 원본 판정/시각, 부재, 권한 거부 또는 재시도 안내. 조회된 것은 **정정 적용 전 원본**이다. 현재 진단·정정 결과로 대체하거나 목록에 합성하지 않는다.

## 서버 계약

`GET /api/scouting-original-check?farmId=…&locationStateId=…&fieldCheckId=…`

- 세 ID는 필수, trim 후1~100자. 누락/초과422.
- 기존 getFarmMember의 현재 ACTIVE membership 및 viewHistory 없으면403. 실제 플랫폼 identity 신뢰 경계는 변경하지 않았다. 테스트 주입 identity를 실제 로그인 검증으로 취급하지 않는다.
- 원본과 location의 farm 일치를 JOIN하고 farm/location/check 세 ID를 함께 제한한다. 없거나 다른 구역/다른 농장 대상이면404.
- 응답 original은 id/farm_id/location_state_id/primary_evidence_code/checked_at만 포함한다. note/actor/photo/JSON은 SELECT하지 않는다.
- 모든 응답 no-store. 조회/스키마 실패는 일반503이며 내부SQL/오류를 반환하지 않는다. 자동 schema 보완 없음.

## 검증 — Node24 로컬

```sh
node --import ./tests/register.mjs --test tests/scouting-original-check.test.tsx tests/scouting-original-lifecycle.test.ts
node --import ./tests/register.mjs --test tests/scouting-ui.test.tsx tests/scouting-hardening.test.ts
./node_modules/.bin/tsc --noEmit --incremental false
npm run lint
npm run build
```

- 신규7/7 PASS: 실제 GET→권한→service→repository를 synthetic `:memory:` binding으로 실행. 51개 합성 check 중50건 밖 원본200, worker/owner 허용, 비회원/다른농장/비활성 거부, 잘못된 farm-location 연결404, 누락/길이/부재, schema 부재503, SQL SELECT-only 및 저장 snapshot 불변을 확인했다.
- 클라이언트: GET 중복 클릭 coalesce, safe projection, 부재/거부/실패 구분, 재조회 초기 데이터 제거, 다른 scope 응답 거부, invalidate 후 늦은 성공·실패 무시. 실제 component 함수의 버튼/컨텍스트 변경/cleanup callback도 synthetic hooks로 실행했다. 이는 React 브라우저/DOM lifecycle 수용 검증은 아니다.
- 관련22/22 PASS: 기존 이력·예찰 hardening. 이 suite의 bootstrap은 테스트용 synthetic memory에서만 수행되며 새 GET 경로 bootstrap과 다르다.
- 최종 타입·lint·빌드 PASS. 빌드의 proxy 환경 안내와 vinext route-classification 안내는 오류가 아니며 외부 서비스 검증 근거가 아니다.

## 남은 게이트

- 기준: parent가 확인한 main3547c552/tree0581e88a 위 history8 스냅샷. 이 executor에서 원격을 새 조회한 것은 아니다. 부모 최초 기준 확인2026-11-04 13:48UTC와 후속 공식 compare22:10UTC를 구분하며, 그 이후 원격 상태는 미확인이다.
- 최초12파일 후보에서는 신규2개 테스트가 로컬 직접 실행만 됐다. 후속 CI 사본에서는 test:workflows에 두 파일을 추가하여 실제 npm script99/99 통과를 확인했다(기존92+신규7). 사진 후보의 package.json은 별도이므로 합칠 때 양쪽 테스트 추가를 모두 보존해야 한다. 원격 CI 실행으로 표현하지 않는다.
- 실제 브라우저/mobile/focus/overflow, 실제 플랫폼 인증, 운영 D1/네트워크/동시성은 NOT_RUN. 기존 접근 거부는 우회하지 않았다.
- 기능 구현은 로컬 후보이며 main 반영/출시 완료가 아니다. 부모의2026-11-04 22:10UTC 공식 compare에서 main3547c552와 identical임을 확인했다. 적용 순서는 이력8 → 단건12 delta → CI3이며, 공유 hunk와 적용/역적용 증거는 외부 split manifest에 기록한다. 사진5의 package 목록을 합친 검증과 원격 게시에는 각각 해당 범위의 후속 절차가 필요하다. 게시에는 별도 승인 필요.
