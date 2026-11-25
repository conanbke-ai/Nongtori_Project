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

---

## 2026-11-24 병해충 카탈로그와 모델/데이터 준비 상태 분리 정책

**Policy status: ADOPTED / Documentation only.** 기존 `app/features/pests/domain/catalog.ts`의 6개 항목(`MITE`, `POWDERY_MILDEW`, `GRAY_MOLD`, `APHID`, `THRIPS`, `OTHER`)은 표시·접수·기록용 카탈로그이며 현재 모두 `capability: RECORD_ONLY`다. 등록이 곧 모델 학습·예측·진단 가능함을 의미하지 않는다.

### 카테고리별 근거와 준비 현황 (2026-11-24, GitHub main에서 확인한 원격 문서 기준)

| 카탈로그 | 확인된 학습 근거 | 현재 AI 사용 가능성 |
|---|---|---|
| MITE 응애 | `MITE-PUBLIC-FIELD-CONTEXT-V001` 및 `MITE-PUBLIC-MORPHOLOGY-V001` 공개 RGB 객체 탐지용 스냅샷 존재 | RGB 연구/참고 수준, 운영 추론 미연결; Thermal-first field training/calibration gate 미통과 |
| GRAY_MOLD 잿빛곰팡이병 | `DATA-PEST-001` 외부 데이터 원래 라벨 `gray_mold` 존재 | 병별 학습·검증·서비스 판독 완료 아님 |
| POWDERY_MILDEW 흰가루병 | 등록된 위 두 공개 데이터셋에 전용 라벨 확인되지 않음 | 학습 스냅샷 확인 필요, RECORD_ONLY |
| APHID 진딧물 | 위 공개 데이터셋에 전용 라벨 확인되지 않음 | 학습 스냅샷 확인 필요, RECORD_ONLY |
| THRIPS 총채벌레 | 위 공개 데이터셋에 전용 라벨 확인되지 않음 | 학습 스냅샷 확인 필요, RECORD_ONLY |
| OTHER 기타·미확인 | 현장 기록/보류 분류, 정답 학습 클래스라고 가정 금지 | RECORD_ONLY |

실제 로컬 또는 미병합 브랜치의 새 데이터 여부는 별도 감사 전까지 **UNKNOWN**으로 유지한다. `DATA-PEST-001`에는 `dry`, `gray_mold`, `scorch`, `Tetranychus Urticae` 라벨이 존재하지만, 증상 라벨과 병해충 진단명을 자동 동치 매핑하지 않는다. 공개 RGB 데이터의 확보/모델 연구 성과를 특정 농가에서의 현장 검증으로 표현하지 않는다.

### 데이터 준비 상태와 모델 서비스 상태는 독립 관리

향후 구현 시 다음 두 개의 구분된 상태축으로 계약화하되, **이번 문서 적용만으로 DB/schema/UI/API를 수정하지 않는다**.

- Data readiness 후보: `NOT_REGISTERED` → `SOURCE_REGISTERED` → `ACQUIRED` → `AUDITED` → `SNAPSHOT_READY` → `FIELD_VALIDATED_DATA` (정의와 진입·퇴출 조건은 기존 데이터 정책과 정합성 검토 후 고정). 원본 미접근/미확인은 `UNKNOWN` 별도 유지.
- Model capability: `RECORD_ONLY`, `RESEARCH_ONLY`, `VALIDATED_NOT_DEPLOYED`, `INFERENCE_ENABLED` 등은 향후 설계 후보이며 기존 `capability: RECORD_ONLY`의 실제 구현과 혼동하지 않는다. 검증된 worker, 체크포인트, 권한·보안·QA 및 배포 승인 전에는 `INFERENCE_ENABLED`로 전환하지 않는다.
- 카탈로그/라벨/데이터셋/모델은 다대다로 연결될 수 있으며, 각 관계에 task(thermal risk/RGB detection/disease classification), class mapping version, source ID, snapshot hash, model/version, license, validation evidence, deployment state를 부착한다.
- UI에서 데이터 미확보/모델 미연결 상태를 숨기거나 임의 confidence/확정 음성 판단을 만들지 않는다. 신규 병해충 종을 추가할 때도 `RECORD_ONLY` 기록 가능 상태와 AI 기능을 분리한다.
- 원본 read-only, 라이선스 확인, 라벨 품질, exact/near-duplicate, capture session·farm·group 단위 누수 감사, immutable snapshot, frozen test, 실제 현장 독립 검증을 순차적으로 통과해야 모델 후보가 된다.

### 우선순위 및 일정

1. **MITE Thermal-first:** radiometric thermal 원본·동일 구역/잎 reference·시간·환경(VPD)·독립 응애 확인 라벨을 연결하고, 확인 양성/음성/미확인 구분. `Health`/`Risk_Status` 및 RGB 미탐을 응애 음성 정답으로 대체하지 않는다. `docs/THERMAL_MITE_RISK_V001.md`의 gate가 우선한다.
2. 기존 공개 데이터셋과 등록 라벨/원본 저작권/스냅샷 상태를 재감사하고 중복 다운로드 금지. RGB 응애 모델은 독립적인 보조 연구로 유지.
3. 잿빛곰팡이병의 확보된 원래 라벨을 검증하고, 흰가루병·진딧물·총채벌레의 부족한 종류별 데이터 출처를 순차적으로 조사한다. 증상과 확정 병해 진단은 구별한다.
4. 별도 모델 고도화/Few-shot 실험은 데이터·라벨·split gate 이후만 수행. 2027-03 포트폴리오 완료 목표를 위해 다종 AI 판독 전체 완성은 V1 출시 필수 조건으로 만들지 않는다.

기존 업로드·예찰·권한·다국어·`UPLOADED_AWAITING_MODEL` 상태와 운영 DB를 보존한다. 작업은 기존 workstream을 먼저 조회하고 중복 브랜치 생성 없이 실행한다.
