# 읽기 전용 legacy evidence Domain view

후속 상태: 아래는 `/workspace/scratch/nongtori-legacy-view-RMOALk`의 독립 mapper 후보 기록이다. 현재 UI 후속 사본에서는 매핑 값을 바꾸지 않고 읽기 presentation 소비자 한 곳만 연결했다. 해당 변경·검증은 `LEGACY_EVIDENCE_READING_UI_CANDIDATE.md`와 ACTIVE_WORK의 최상단 절을 따른다. 원래 mapper 후보 파일은 수정하지 않았다.

## PRECHECK / 수용 범위

root 단일 writer. 기반은 frozen finding-picker6 후보와 그 선행 사진/이력/단건/조합이다. 별도 `/workspace/scratch/nongtori-legacy-view-RMOALk` 사본에서만 작업한다. 기존 사용자 원본·index와 각 후보는 고정 보존한다. 알려진 main3547c552의 parent 확인은2026-11-04 22:10UTC이며 이후 원격은 미확인이다.

canonical STATE_DESIGN §6, DB_SCHEMA_V1 §8·§13의 legacy code 보존/mapper/점진 전환에 한정한다. 원본 입력과 유도 결과를 구분하는 독립 Domain 읽기 모델이며 UI/API에 연결하지 않는다. 새 typed finding 저장·CASE·정정·receipt·권한·스키마 의미를 만들지 않는다.

## 읽기 모델

- `source.kind=LEGACY_CODE_INPUT`, `source.code`는 전달된 문자열을 그대로 보존한다. 실제 DB에서 수집했다는 provenance 주장은 아니다. 비문자열은 code=null 및 INVALID_INPUT으로 처리하고 원본 객체를 복사하지 않는다.
- `derived.kind=DERIVED_LEGACY_READING`, mapperVersion과 status를 따로 반환한다. 기존8code만 RECOGNIZED. unknown/invalid의 빈 findings는 '관찰 없음'이나 음성 판정이 아니다.
- 직접 응애 확인만 canonical 예에 따라 PEST/SPIDER_MITE로 유도한다. 다른 해충·병해·환경생리는 해당 관찰 family만 유도하고 issueCode는null이다. leaf damage/의심 흔적/판단 어려움은 이 보수적 view에서 UNKNOWN으로 남기며 원본code를 잃지 않는다. CASE 분류 mapper를 대체하지 않는다.
- NONE_VISIBLE은 당시 관찰 범주일 뿐 definitiveNegative=false를 유지한다. 모든 certainty/severity는null이며 수치나 확인 수준을 추정하지 않는다.
- secondaryEvidence와 다른 metadata는 읽지도 복사하지도 않는다. 원본의 임의JSON, 사진 접수target, 별도 역할/농장 정보에서 종이나 권한을 추론하지 않는다.
- 순수 함수와 type-only domain import뿐이며, 출력은 매번 새 객체다. DB·시간·네트워크·UUID·authority 생성 없음.

## 노출·완료 한계

기존 raw history API는 JSON·메모·작성자를 포함한 raw 행을 반환하며, 이력 UI에서만 안전 투영한다. 이 mapper는 그 API에 연결되지 않았으므로 서버 노출이나 권한 보안을 고친 것이 아니다. 원본 단건 API의 기존 최소응답/권한도 변경하지 않는다.

복수 종별 저장, typed validation·CASE 집계·정정 의미·receipt canonical version 변경, 기존 데이터 이주는 계속 별도 계약/승인 대상이다. 새 UI/브라우저 기능·배포·기능 활성화는 없다.

## 검증 상태

```sh
node --import ./tests/register.mjs --test tests/legacy-field-evidence-view.test.ts
npm run test:workflows -- --test-name-pattern='^legacy view:'
./node_modules/.bin/tsc --noEmit --incremental false
npm run lint
```

- 표적5/5 PASS:8code 명시매핑, 원본/derived 출처 구분, unknown/invalid/prototype이름, secondaryJSON·authority getter 미접근, frozen입력 불변, 출력객체 독립, runtime import·소비자 부재를 확인했다. 외부/DB 호출 없는 합성 값 검사다.
- CI의 기존 test:workflows 목록15파일을 모두 유지하고 새 test1파일을 끝에 추가했다. 위 npm 명령에서는 필터 인자가 적용되지 않아 실제115/115 PASS(기존110+신규5, skip0)를 관측했다. 표적만 실행됐다고 표기하지 않는다. 이후 전체 재실행은 하지 않았다. 원격CI/Node22 실행은 NOT_RUN이며 로컬 Node24 결과다.
- TypeScript PASS. 최초 lint의 Next no-assign-module-variable 오류1건은 테스트 변수 module을 modulePath로 바꿔 해결했고 최종lint PASS다. assertion/검사 억제 없이 수정 후 표적5개를 재실행해 통과했다.
- 독립 읽기 검수에서 P1/P2 없음. 검토자는 실행/수정하지 않았다. 최종 ACTIVE_WORK를 포함한 고유5파일 차분과 해시·외부 patch를 검증한다. Advisor 설치 실행 경로는 unavailable이며 상담 완료로 표현하지 않는다.
- UI/API/Service/Repository/CASE/receipt·기존권한코드는 바뀌지 않았다. Build는 이번에 재실행하지 않았으며 기존 상위선택 후보 빌드 통과와 구분한다. 브라우저/실계정/운영D1/실데이터·외부전송·게시·배포는 NOT_RUN/미실행이다.

다음 단계는 이 독립 mapper의 별도 검수/게시 범위 판단이다. 이번 후보는 UI/API에 연결하지 않는다. 새 typed 저장·복수 CASE·정정 의미는 HOLD이며 mapperVersion은 receipt canonical_version이나 새 API 저장 버전을 바꾸는 값이 아니다.
