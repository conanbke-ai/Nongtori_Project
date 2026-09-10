# 병해충·판독 협업 흐름 수정 — 2026-09-08

후속 전달: 사용자의 운영 반영 요청에 따라 이 문서의 기능은 기존 운영 Site version 23에 배포했다. 배포 후 `capture_sessions.pest_code` 열 존재를 읽기 전용으로 확인했다. 아래 미배포/승인 대기 언급은 초기 검증 시점 이력이며, 최종 근거는 [운영 현황/커서 후속 기록](OVERVIEW_AND_CURSOR.md#후속-공통-원본-재사용-및-운영-반영)을 따른다.

## 판정과 기준

`IN_PROGRESS`: `main`은 `d276c9e`, 실행 소스는 기존 `feat/application-source-integration` / Draft PR #2의 `3223b29`에 있다. 새 branch를 만들지 않고 같은 workstream을 이어간다. 확인한 remote branch는 main 포함 3개, ACTIVE workstream은 1개이며 기존 app/db lease 범위다. 로컬의 다른 편입 checkout과 Site 원본은 수정하지 않았다.

사용자가 지적한 세 요구는 실제 코드에서 누락/제한되어 있었다. 응애 SQL 필터가 다른 병해충을 제외했고, 영상 댓글은 응애 prediction이 있어야 열렸다. 수확일지는 판독 기록 안에 있었다.

## 완료 기준 및 구현

- 병해충 종류를 등록하면 사진 접수, 목록 필터, 종류별 건수와 현장 확인이 같은 catalog를 따른다. 응애, 흰가루병, 잿빛곰팡이병, 진딧물, 총채벌레, 기타·미확인이 기본 대상이다.
- catalog 등록은 AI 모델 지원을 뜻하지 않는다. 검증된 inference worker가 연결되지 않은 현재 상태는 `RECORD_ONLY`로 명시한다. 접수 시 결과/confidence/모델 실행을 만들지 않는다.
- 기존 inference task/class label은 공통 mapper가 해석한다. 한국어 응애 복합어와 영어 legacy alias를 보존하며 class label이 task보다 우선한다. 알림 중복 제거와 현장 확인 이력은 `inference run + track + pest code` 기준이다. 과실 품질 판독은 병해충 건수에서 제외한다.
- 수확일지는 `농장관리 → 수확일지`에 있다. 기존 농장/품목 범위와 HarvestLog API를 유지한다.
- 모든 판독 세션에 댓글/답글을 연결한다. 분석 대기·실패·과실·병해충 여부가 댓글 작성 조건이 되지 않는다. 영상 장면별 의견은 별도 버튼으로 보존하고 비응애 prediction도 지원한다.
- 같은 농장 OWNER/WORKER가 서로 댓글을 조회하고 답글을 남긴다. 기존 서버 권한을 유지하며 수정은 본인, 삭제는 본인 또는 농장 구성원 관리 권한 보유자만 가능하다. 다른 농장/세션/장면의 댓글에 답글을 붙일 수 없다. 댓글 새로고침은 명시적 버튼이며 폴링을 추가하지 않았다.

## 변경 경로

| 경로 | 책임 |
|---|---|
| `app/features/pests/domain/catalog.ts` | 종류/별칭/다국어 이름, 확인 결과 계약 |
| `app/features/pests/application/pest-service.ts` | 종류별 목록·집계 및 현장 확인 흐름 |
| `app/features/pests/infrastructure/` | class mapping SQL, 동일 기준의 목록·건수·저장 Repository |
| `app/features/pests/presentation/` | 기존 theme을 따르는 스타일과 다국어 문구 |
| `app/features/records/domain/record-policy.ts` | 세션/장면별 댓글 범위 계약 |
| `app/features/records/infrastructure/record-target-repository.ts` | 농장 범위 안에서 판독 대상/댓글 조회 |
| `app/components/PestCaptureForm.tsx`, `PestAlertReview.tsx`, `RecordNotes.tsx` | 범용 접수·현장 확인·댓글 UI |
| `app/components/FarmerDashboard.tsx` | 종류 필터, 판독 댓글 진입, 농장관리 수확일지 배치 |
| `tests/` | 실제 API/권한 코드와 SQL을 실행하는 격리 SQLite 검증 |

기존 capture controller와 댓글 번역/수정 handler의 일부 직접 DB 접근은 유지된다. 이번 변경은 앱 전체의 목표 계층 구조 전환 완료를 의미하지 않는다.

## API와 저장 호환성

- `GET /api/farmer-dashboard?pestCode=...`: 생략 시 전체 병해충. summary는 농장 전체, pagination은 선택 종류 기준. `alerts[].pest_code` 추가.
- `POST /api/pest-capture`: multipart `farmId`, `itemId`(선택), `pestCode`, `rgbImage`, `thermalImage`(선택). 선택 종류를 `capture_sessions.pest_code`에 저장한다. 상태는 기존 `UPLOADED_AWAITING_MODEL`이다.
- `POST /api/alert-reviews`: `TARGET_CONFIRMED`, `NOT_TARGET`, `RECHECK`를 지원한다. 기존 `MITE_CONFIRMED`/`NOT_MITE`는 응애에만 허용한다.
- `/api/record-notes`: GET/POST/PATCH/DELETE. 기존 요청/응답 계약을 유지하면서 모든 판독 세션·prediction을 지원한다.
- `/api/record-evidence`: 같은 농장에 속하는 비응애 prediction의 근거 이미지도 조회한다.
- `/api/operation-history`: `pest_code`, 세션 댓글 `note_count`를 추가한다.
- 기존 `/api/mite-capture`, `/api/mite-record-notes`, `/api/mite-evidence` 및 Mite 컴포넌트 export는 호환용으로 유지한다. 이전 배포 클라이언트가 모두 전환된 뒤 별도 제거할 수 있다. 응애 접수의 누락된 `pestCode`만 legacy endpoint에서 MITE로 기본 처리한다.
- `mite_record_notes`와 번역 테이블 이름/내용은 보존한다. 기존 댓글 ID, 원문, 답글, 작성자 snapshot을 이관하거나 재작성하지 않는다.

## Migration과 기존 제약

새 migration `0015_pest_capture_targets.sql`은 nullable `capture_sessions.pest_code` 한 열만 추가한다. 기존 기록은 NULL을 유지한다. 운영 DB에는 아직 적용하지 않았다.

Drizzle generate 실행 시 기존 `0009` 이후 snapshot 공백 때문에 이미 별도 migration/runtime bootstrap이 다루는 unrelated DDL도 생성되었다. 새로 생성된 미적용 0015 SQL과 snapshot만 이번 열 추가 delta로 제한했다. 기존 0000–0014 SQL·snapshot·journal entry는 변경하지 않았다. 0015 snapshot은 0009 snapshot에 해당 열만 추가한 것이다. 기존 schema drift의 정리는 별도 과제로 남는다.

기존 0014는 runtime bootstrap이 생성하는 `farm_members.joined_at`에 의존하므로, 기존 migration들만 빈 DB에 순서대로 적용하는 경로는 실패한다. 테스트는 기존 실제 초기화 경계인 0000–0013 → `ensureSchema()` → 0014–0015를 실행했다. 신규 빈 DB에 migration만으로 설치하는 문제가 해결됐다고 주장하지 않는다.

기존 문자 알림 trigger/전송은 응애 계약을 유지한다. 이번 수정은 병해충 목록·접수·현장 확인·댓글 범위이며, 다른 병해충의 SMS 발송이나 모델을 활성화하지 않는다.

## 실행 검증

- `node --import ./tests/register.mjs --test tests/pest-records.test.ts`: 5개 통합 시나리오 통과. 모든 기본 병해충 접수, 비응애 목록/건수/페이지, 응애 중복 제거 및 한국어 legacy label, 현장 확인 결과 분리, OWNER/WORKER 댓글·답글, 수정·농장·세션·장면 범위, legacy endpoint를 실제 route/권한 코드와 production SQL로 확인했다.
- 테스트 DB는 메모리 SQLite, 계정/사진은 명시적인 `TEST_ONLY` fixture. 실제 농장·외부 원본·공용 DB 및 외부 번역/문자 API는 사용하지 않았다. Cloudflare binding 인터페이스만 로컬 adapter로 대체했다.
- `tsc --noEmit --incremental false`, `eslint . --ignore-pattern dist --ignore-pattern .next`, Sites build helper의 `vinext build`, `git diff --check`를 실행했다.
- 브라우저/모바일 시각 검수, hosted D1/R2와 실사용 계정 간 검증, 모델 성능 검증은 미실행. 현재 서비스 배포와 PR 병합은 수행하지 않았다.

## 원격 반영 상태

로컬 기능/검증 커밋은 `92d15d9`, `e6e49cf`, `1bfb4f8`, `60b35e8`이다. GitHub push는 자동 승인 검토에서 원격 저장소 전송 및 branch 변경에 명시적 승인이 부족하다는 이유로 차단됐다. 읽기 전용 재확인에서 PR #2 head는 여전히 `3223b29`다. 사용자 승인 전까지 PR 반영·배포 완료로 취급하지 않는다.
