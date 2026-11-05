# 기존 기록 해석 출처 — 읽기 UI 후보

## PRECHECK / Product Flow

STATE_DESIGN §6: 현장 기록은 관찰 사실이며 강한 음성으로 승격하지 않는다. UI_V1_CONTRACT §4: 상세/이력의 보조 정보는 확장 영역에 둔다. 기존 권한으로 이미 받아 안전 투영한 field check code만 사용한다. source code와 derived reading을 명확히 구분하는 작은 disclosure를 추가한다.

root 단일 writer. `/workspace/scratch/nongtori-reading-ui-1c8aUI`는 frozen mapper5 사본이며 기존 사진/이력/원본/상위선택/조합/mapper 후보와 사용자 원본/index를 수정하지 않는다. 알려진main3547c552 확인은 parent의2026-11-04 22:10UTC 근거이며 이후 원격은 미확인이다.

수용 기준:

- 이력 현장 확인 또는 실제 단건 조회 성공 기록에서만 확장 버튼 표시. 접힌 상태가 기본이며 열기/닫기는 네트워크·저장·재시도를 유발하지 않는다.
- 원문 code는 그대로 React text로 escape하여 보여준다. unknown 코드는 해석 불가라고 명시하고 임의 종·정상·음성 판정을 만들지 않는다.
- '기존 기록에서 해석됨', 원문 code, mapper version을 구분하고 새 진단·확정 음성이 아님을 명시한다. 알려진 종도 원문 코드의 대상 표기로만 표시한다. secondaryEvidence/메모/작성자를 가져오지 않는다.
- 이력 loading/error/stale와 원본 loading/denied/missing/error, 컨텍스트 전환·지연 응답 경계는 기존 로직을 유지한다. 정정 행 자체를 새 현장 확인으로 해석하지 않는다.
- 4개 언어, native button aria-expanded와44px/focus/긴 code 줄바꿈을 사용한다. 실제 브라우저·스크린리더·mobile acceptance는 이번에 실행하지 않는다.
- Domain 매핑 값은 그대로이며 소비자는 이 읽기 presentation 한 곳만 허용한다. API/Service/Repository/CASE/정정/receipt/권한/스키마 변경 없음.

## 보안·데이터 한계

기존 raw history API는 JSON·메모·작성자를 포함한 raw 행을 반환하며 UI에서만 투영한다. 이 변경은 API의 서버 노출을 고치거나 새 권한 보안을 추가한 것이 아니다. 단건 API의 기존 최소응답과 farm/location/member/viewHistory 경계도 변경하지 않는다.

실데이터·운영DB·실계정·외부전송·유료AI·브라우저·원격게시·병합·배포는 제외한다. 종별·복수 finding 저장·CASE 정책은 계속HOLD다.

## 검증

```sh
node --import ./tests/register.mjs --test tests/legacy-evidence-reading.test.tsx tests/legacy-field-evidence-view.test.ts tests/scouting-ui.test.tsx tests/scouting-original-check.test.tsx tests/scouting-original-lifecycle.test.ts
./node_modules/.bin/tsc --noEmit --incremental false
npm run lint
npm run build
```

- 신규5개 포함 표적/관련31/31 PASS. 접힘/열기/닫기 무네트워크 callback, 8code 원문/해석 출처/경고, unknown HTML escape·공백보존,4언어·CSS44px/wrap/focus, fieldChecks만연결·정정원본anchor·stale/error보존을 확인했다.
- 기존 Original component callback 검사에 초기/다른컨텍스트/loading에서 reading부재, 실제 scoped GET 성공 후 reading존재를 추가했다. 기존 API 권한·wrong farm/location·noDDL/noWrites·늦은응답 검사는 변경 없이 통과했다. 원문코드는 reader가 안전 투영한 값만 전달한다.
- TypeScript/lint/build PASS. 기존 full115는 반복하지 않았다. package의 기존16개 test파일 목록을 유지하고 새 file1개만추가했다. 실제 App workflow 트리거·권한·명령은 변경하지 않았다. 원격CI/Node22는 NOT_RUN이다.
- Domain module은 consumer상태 주석만 변경했고 매핑/입출력 구현은 바꾸지 않았다. 이전 no-consumer 테스트를 정확히한곳 `presentation/LegacyEvidenceReading.tsx`만 허용하도록 갱신했다. API/Service/Repository 등 다른 소비자가 생기면 실패한다.
- 독립 읽기 검수 P1/P2 없음. 검토자는 실행/수정하지 않았다. 실제 브라우저·모바일·포커스·스크린리더·overflow는 NOT_RUN이며 SSR/합성hook/CSS검사를 해당 수용 PASS로 주장하지 않는다. 빌드의 proxy 및 route-classification 안내는 오류나 실제 외부 검증의 증거가 아니다.
- 모든 선행 후보·사용자 원본/index와 서버/권한/DB/state/receipt 파일은 hash/delta로 보존 확인한다. source 신규영역은presentation, domain은주석, 그외tests/CI목록/후보문서뿐이다. Advisor 전용 실행 경로는 unavailable이며 공식 상담을 수행했다고 쓰지 않는다.

다음 실행 상태는 로컬 IMPLEMENTED / READY_FOR_WORK_QA다. 최신 원격 대조·후보별 분리 게시 승인과 접근 가능한 공식 브라우저 수용 검증은 별도 게이트다. 이번에는 새 branch/commit/push/PR/main/배포나 실제 데이터를 사용하지 않았다.
