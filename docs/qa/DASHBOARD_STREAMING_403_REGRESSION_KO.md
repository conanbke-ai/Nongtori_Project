# 미종료 403 본문의 Dashboard 회귀 검사

## 목적과 제품 계약

403 상태를 확인한 Dashboard는 오류 본문이 끝날 때까지 기다리지 않고 비공개 화면을 차단해야 합니다. 본문을 소비·잠금·취소하는 것이 이 UI 보호의 선행 조건이 아닙니다. 차단 이전의 늦은 조회 성공은 명시적인 현재 권한 재확인을 대신할 수 없습니다. 일시적503/네트워크 오류에서 기존 stale 화면을 유지하는 계약은 바꾸지 않습니다.

이 회귀는 제품 코드의 재구현이 아니라 실제 `FarmerDashboard`의 요청/오류 처리를 실행합니다. 기존 `dashboard-access-denied.test.tsx`의 합성 hook 검사와 실제 React DOM을 mount하는 브라우저 검사를 분리합니다. hook 검사를 DOM/브라우저/서버 권한 검증으로 부르지 않습니다.

## 정식 진입점

```sh
npm run test:dashboard-stream403
npm run test:dashboard-stream403:runner
NONGTORI_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:dashboard-stream403:browser
```

실제 브라우저 진입점은 현재 제공된 **Linux 환경만 지원**합니다. `ps -o pid=,stat=,comm= --ppid <현재 PID>`와 설치 Chromium이 필요합니다. OS와 정확한 ps 인자를 브라우저 생성 전에 확인하며, 준비 실패나 다른 OS에서는 중단합니다. Windows/CIM·대체 프로세스 조회·경로 우회를 새로 지원하지 않습니다. hook 및 메모리 함수 기반 실행기 회귀는 브라우저를 생성하지 않습니다.

세 npm 진입점은 다음처럼 분리합니다. 브라우저 도구가 없는 일반 실행에서 hook·순수 실행기 회귀를 막지 않습니다.

1. `test:dashboard-stream403`: 기존 테스트 파일에서 이름이 `미종료 403 본문에서도`로 시작하는 hook 회귀1개.
2. `test:dashboard-stream403:browser`: 사전 도구가 필요한 `tests/browser/dashboard-stream403.test.mjs`의 실제 DOM 회귀1개.
3. `test:dashboard-stream403:runner`: `dashboard-stream403-runner.test.mjs`의 순수 오류 처리 회귀. 실제 ps·파일 쓰기·브라우저 대신 메모리 함수를 주입합니다.

기존 `test:workflows`는 이미 hook 파일을 포함합니다. 순수 실행기 회귀 파일만 목록에 한 번 추가하며 실제 브라우저 파일은 추가하지 않습니다. workflow 트리거는 변경하지 않습니다. 전체172개를 반복하기 위해 만든 명령이 아닙니다.

## 실행 전 준비와 실패 처리

- 프로젝트의 기존 설치 의존성 및 Node22.13 이상이 필요합니다.
- 브라우저 검사는 정상 Node 해석 경로에 사전 제공된 Playwright와 `NONGTORI_CHROMIUM_EXECUTABLE`에 지정한 설치 Chromium을 요구합니다. 현재 package.json에 Playwright 의존성을 새로 추가하거나 설치 명령을 넣지 않았습니다. 도구가 없으면 오류로 중단하며 skip이나 자동 설치로 통과시키지 않습니다.
- cloud 실행기가 표준 `NODE_PATH`로 도구를 제공하는 경우, 자식 실행기의 환경 allowlist가 그 제공값을 누락하지 않아야 합니다. 원래 제공된 값을 그대로 계승하며 임의 경로를 추가/하드코딩하거나 별도 경로 탐색을 하지 않습니다. 로컬 의존성으로 정상 제공되는 환경에는 이 변수가 필수인 것은 아닙니다.
- 프로젝트의 공식 `npm run build`에서 생성한 root CSS가 `dist/client/_next/static/css/index.*.css`에 하나 있어야 합니다. 실행기가 빌드를 자동 시작하지 않습니다. 제품/style 입력이 변경됐다면 허용된 절차로 새 빌드가 먼저 필요합니다.
- 산출물은 기본적으로 새 임시 디렉터리에 저장합니다. 원하는 경우 존재하지 않는 `NONGTORI_QA_OUTPUT_DIR`을 지정할 수 있습니다. 기존 결과를 덮어쓰지 않습니다.
- 브라우저 조작/관측은4초, launch는8초, Node 테스트는30초로 한정합니다. 정리는 단계별4초로 제한하며 stream·mount·context·browser 정리를 각각 시도하고 실패를 기록합니다. 정리 불명은 PASS가 아닙니다.
- 사후 ps·보존 관측 실패는 최초 테스트 오류·정리 오류를 덮지 않고 별도 필드로 남깁니다. 그 경우에도 영수증 쓰기는 한 번 시도하며 자원 종료 PASS를 주지 않습니다. 영수증 쓰기 자체가 실패하면 콘솔/TAP에 최초·정리·사후·쓰기 오류를 함께 남기고 테스트를 실패시킵니다. 실패한 쓰기를 반복하거나 기존 영수증을 덮지 않습니다.

현재 일반 App CI에는 브라우저 실행기 준비가 보장되지 않습니다. 따라서 기존 workflow에서는 hook·순수 실행기 회귀가 연결되고, 브라우저 회귀는 도구와 빌드가 준비된 Linux QA 실행기에서 명시 명령으로 실행합니다. 이 후보가 브라우저 검사를 일반 CI에서 이미 자동 실행했다는 뜻은 아닙니다. CI 브라우저 준비/의존성 정책은 별도 범위입니다.

최초 편입 후보에서 hook은 통과했지만 브라우저 생성 전에 `MODULE_NOT_FOUND: playwright`가 났습니다. 기존 cloud는 표준 `NODE_PATH`로 Playwright를 정상 제공했으나 실행기의 환경 allowlist가 이를 누락한 것이 확인됐습니다. 실패 기록은 그대로 보존하고 v2에서 제공값의 계승 계약과 두 진입점 분리만 교정했습니다. 테스트의 DOM/본문/늦은 응답/요청 차단 단언은 약화하지 않았습니다. 이 설명은 접근 거부·PC/ZIP/bwrap 제한의 우회 허용이 아닙니다.

## 단언과 합성 경계

hook 회귀는 native Response/ReadableStream의 미소비·미잠금 상태에서 hidden/inert가 반영되고, 오래된 Dashboard 성공 응답이 이를 풀지 못함을 확인합니다. finally에서 합성 stream을 취소하고 기존 fixture의 effect·전역 mock을 복구합니다.

브라우저 회귀는 실제 프로젝트의 Dashboard를 상대 경로로 import합니다. 특정 scratch 경로나 고정된 옛 소스를 실행하지 않습니다. 합성 농장A의 예찰 행을 표시한 뒤 목록 GET을 지연시키고, 정확한 Dashboard 요청에 미종료 native403 Response를 공급합니다. 기존 DOM 소유자가 유지되면서 비가시/inert가 되고, 재확인 패널이 나타나며, 늦은 목록200의 marker가 화면에 반영되지 않아야 합니다.

API는 동일 browser realm의 메모리 fetch/Response만 사용합니다. 문서는 route.fulfill로 공급하며 그 밖의 실제 요청은 차단하고 페이지를 종료합니다. 합성 fixture는 POST도 허용하지 않습니다. service worker는 설치하지 않습니다. 다음 경계를 단언합니다.

- 논리 DOM 조건1개와 내부 단언9개.
- 합성 GET5건, POST/추가 자동 요청/브라우저 오류0건.
- 생산자가 close/error하지 않은 본문에서 bodyUsed/locked/cancelled가 false인 동안 실제 차단 DOM 확인.
- 늦은 목록200 뒤 차단 유지·marker 비반영.
- unmount1회, QA stream 취소 및 자원 정리, 제품 app/package/lock의 전후 동일성.

fixture의 `producerClosed:false`는 생산자가 close를 호출하지 않았다는 입력 계보입니다. 실제 HTTP transport 상태 API가 아닙니다. 실제 GET을 취소한 검사나 운영 권한 검증으로 확대하지 않습니다.

## 출처와 남은 한계

최초 근거는 b008 기준 cloud 합성 Chromium1/1 검사입니다. 이 후보는 해당 fixture/단언을 저장소 상대 경로·Node test·npm 진입점으로 편입한 것입니다. 제품 동작·CSS·기능 flag·저장/권한 계약은 변경하지 않습니다.

정상 완료403, 503/네트워크 stale, 기존 늦은 응답 계약은 기존 회귀와 영수증을 재사용합니다. 실제 HTTP `response.finished()` 완료 BLOCKED, BFCache HOLD, 운영 인증/DB·SSR·첫 paint·실기기 수용은 해결하지 않습니다. 새 검사 통과가 그 상태를 변경하지 않습니다.

검수는 이번 담당자의 자체 검토이며 독립 검수로 표시하지 않습니다. 게시·CI 브라우저 환경 추가·main 병합·배포는 각각 별도 승인/범위 확인이 필요합니다. 기존72px CSS 승인 요청과 dock 여백 후보는 이 테스트 후보와 분리합니다.


## N-A 통합·신뢰성 checkpoint — 2026-11-25

- 정책은 `conanbke-ai/Tori_Common_Project@df0331220f6eae2b802bed612ec306ac20893c1a`의 운영 §26–32, Credit Guard §13, Transaction Recovery Standard를 읽기 참조했다. 제품 안에 정책 본문을 복제하지 않았다.
- 실제 원격 Git 조회: main `917aa934380407a97b48e7a0fc0347dae6fa685f`, #109 `ceb6c9a94108b638a024c84fade4a1e0ef2e7d41`, #113 `849c887e98ce1c6d6295ea0be9b442e0693ee4db`. main은 #112 merge이고 #109에 포함되며 #109는 #113의 조상이다. #113의 고유 변경은 사진 Application/Adapter 분리, Scouting Port, HarvestLog 이동의 3커밋/16경로다. 이를 중복 cherry-pick하거나 main에 재구현하지 않는다.
- #113의 실제 Draft 대상은 #109 브랜치다. 제품 수정은 #109 범위로 분리하고 #113은 최신 #109를 채택한 결합 후보로 검증하는 순서다. Draft 해제·main 병합·운영 배포 승인은 아니다. 과거 PR 설명의 f8934bd와 사용자 제공 CI 성공은 현재 SHA의 독립 CI 관측으로 재해석하지 않는다.
- 검증 위치는 `/workspace/scratch/nongtori-na-integration-20261125`의 실제 Git worktree다. 원래 `/workspace/Nongtori_Project` work/3547c552의 수정·미추적 517파일과 index는 보존한다. Windows 정식 작업본 동기화는 NOT_RUN이다.

### 새 반례와 최소 수정

기존 snapshot ID 비교만으로는 A→B→A의 마지막 A 확인 전에 cached A 사진 폼이 다시 활성화된다. 두 진입점×성공/실패 4검사가 수정 전 실패했다. 명시 농장 선택 변경에만 `farmSnapshotReady=false`, 현재 request sequence의 성공 apply에만 true를 적용했다. 두 사진 폼과 mutation actor가 같은 readiness를 사용한다. 같은 농장 refresh는 폼 key/readiness를 바꾸지 않으므로 기존 sending/uncertain owner를 유지한다. 서버 인가·POST·요청 키·자동 재전송·스키마·모델 코드는 변경하지 않는다.

최종 회귀는 두 진입점×성공/실패×두 응답 순서 8건과 status 탭의 actor 왕복 전환 1건이다. 최신 확인 실패 후에는 폼이 계속 닫히고 로딩은 끝나며 기존 명시 재시도로 회복한다. 오래된 B 응답은 A 확인을 대신하거나 완료된 A를 덮지 못한다. 초기 actor 검사는 사진 탭에 존재하지 않는 status 컴포넌트를 찾는 fixture 오류로 4건 실패했으며, 기대값을 낮추지 않고 별도 status 탭 검사로 분리했다. 실패 로그는 삭제하지 않았다.

- `node --import ./tests/register.mjs --test tests/dashboard-access-denied.test.tsx tests/pest-capture-guidance.test.tsx`: 최종 59/59. 기존 403/권한·다국어·불명 결과 latch 검사를 포함하는 synthetic hook/SSR 경계이며 실제 React DOM/mobile 검증은 아니다.
- `npm run test:scouting-idempotency:local-d1`: 3/3. 공식 Miniflare D1에서 네 예찰 handler의 동일 receipt replay, 다른 payload 충돌/권한 재확인, quota와 실제 batch rollback을 검증했다. 실제 R2·운영 D1이 아니다.
- 전체 workflow·타입/lint·build의 최종 명령/결과와 정확한 파일 fingerprint는 이번 작업 영수증을 따른다. 실제 브라우저는 이전 sandbox 차단을 재실행하지 않았고, 현재 공식 desktop 제어 도구도 제공되지 않아 NOT_RUN이다. HTTP 완료 BLOCKED·BFCache HOLD는 해제하지 않는다.

### 별도 미해결 gate — 완료로 승격 금지

1. 사진 save의 commit 뒤 응답 유실: 실제 `recordPestCapture`에 Port 대역으로 저장 완료 후 reject를 주면 catch가 R2 대역의 참조 파일을 지운다(안전 불변식 1FAIL). 실제 D1/R2 사고 재현이 아니라 조건부 장애 진단이다. 확정 rollback과 불명 결과를 구별하는 저장 계약·대사 없이 일반 catch 삭제를 안전하다고 할 수 없다.
2. 사진 영속 중복 방지: 동일 입력을 두 번 호출하면 session 두 건이 생긴다(요구 불변식 1FAIL). 사진 경로에는 durable request identity/receipt가 없다. 예찰 handler의 keyed receipt 3/3 성공을 사진 업로드의 중복 방지로 확대하지 않는다. remount/재진입 뒤의 uncertain 복구도 미완료다. 기존 PR의 DB/schema·새 저장 활성화 제외 조건을 보존하여 이번 UI 수정에 새로운 저장 계약을 섞지 않는다.
3. `ML_INFERENCE_CONTRACT_V001`: 확인한 main/#109/#113, ML branch df8d69ee 및 qa-contract branch 6e01008a에서 해당 원문이 없다. 기존 farm/snapshot/QA contract를 그 문서로 가장하지 않는다. N-B 담당의 정확한 파일 경로·SHA와 입력/출력/실패/버전·단위 계약이 제공되어야 웹 DTO를 연결한다. 모델·가격 담당 소스는 수정하지 않았다.

합성 진단 2FAIL과 실제 D1 3PASS, workflow PASS, 모바일/HTTP/BFCache 미완료는 별개다. 이번 snapshot 수정만의 검증·Draft 게시 판단이 혼합 PR 전체 통합 승인이나 서비스 출시를 뜻하지 않는다.
