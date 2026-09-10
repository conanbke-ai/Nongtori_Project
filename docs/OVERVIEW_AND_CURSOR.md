# 운영 현황과 공통 커서 수정 — 2026-09-08

현재 전달 상태: 사용자 요청에 따라 기존 운영센터에 version 23을 배포했으며, Sites의 `succeeded` 응답과 운영 URL을 확인했다. 아래 초기 점검의 version 22/미배포 상태는 수정 전 이력이다. 최종 공통 커서 연결과 배포 근거는 마지막 절을 따른다.

## 요청과 실제 누락

기존 `feat/application-source-integration` / Draft PR #2 작업을 이어간다. 사용자는 운영 현황에서도 응애가 여러 병해충 중 하나로 보여야 하고, 화면이 단조로우며, 공통 고양이 발바닥의 `뾰잉!` 커서가 빠졌다고 지적했다.

첨부 화면은 서비스의 기존 응애 전용 카드와 일치한다. 앞선 범용 병해충 수정은 아직 로컬에만 있으며 운영 Site는 version 22다. 로컬 코드에도 상단 경고 요약에 응애 이름이 고정되어 있었고, 종류 목록은 펼쳐야 보였다. 공통 커서는 문서 계약만 있고 앱 layout에는 구현이 연결되지 않았다.

## 반영 내용

- 운영 현황에 catalog/API가 제공하는 종류별 카드를 항상 표시한다. 기본 항목은 응애, 흰가루병, 잿빛곰팡이병, 진딧물, 총채벌레, 기타·미확인이다. 종류를 클릭하면 해당 병해충 관리 필터로 이동한다. 추가 항목은 같은 catalog와 집계 계약을 사용한다.
- 상단 경고 요약은 실제 확인 필요 기록이 있는 종류 이름을 함께 표시한다. 제목과 전체 기록 버튼, 메타데이터에 응애 전용 설명을 사용하지 않는다.
- 건수는 기존 농장별 API 집계다. 로딩·농장 미연결·오류에는 `—`와 해당 상태를 표시한다. `0건`은 저장된 확인 필요 기록 수이며 현장에 병해충이 없다는 의미가 아님을 설명한다. 종류 노출을 AI 모델 지원으로 표현하지 않는다.
- 운영 현황의 병해충 영역에는 하늘색, 수확 과실 영역에는 딸기 코랄을 사용한다. 유형 아이콘과 작은 과실 그림, 건수/버튼의 위계를 더한다. 기존 표준 농토리 캐릭터는 유지한다.
- 루트 layout은 확인된 공통 `ToriCatPawCursor` 원본을 그대로 연결한다. 4개 toe bean과 고양이 중앙 패드, 42px 크기, float/클릭 `뾰잉!` 애니메이션은 원본과 동일하다. 농토리에서는 코랄 색상만 지정한다.
- fine pointer, 입력창·편집 가능한 영역, dialog, 창 이탈, reduced-motion 처리는 공통 원본의 동작을 따른다. 농토리용 이벤트 처리나 별도 모션을 추가하지 않는다.

앞선 수확일지 이동과 판독 기록별 농장주/작업자 댓글·답글은 그대로 포함한다. API·권한·DB 변경을 추가하지 않았다.

## 경로와 책임

| 경로 | 책임 |
|---|---|
| `app/features/pests/presentation/PestOverviewCard.tsx` | 범용 종류별 카드, 조회 상태, 확인 필요 종류 요약 |
| `app/features/pests/presentation/overview.css` | 운영 현황의 하늘색/코랄 시각 구분과 반응형 카드 |
| `app/features/pests/presentation/text.ts` | 한국어·베트남어·태국어·중국어 표시 문구 |
| `app/ui/tori/tokens.css` | 기존 TORI 가이드의 농토리 색상 토큰 |
| `app/ui/tori/ToriCatPawCursor.tsx`, `cursor-theme.css` | 공통 원본을 연결하는 얇은 wrapper와 농토리 색상만 지정 |
| `vendor/tori-ui/` | 검증한 원본 컴포넌트·스타일과 출처/버전을 변경 없이 보관 |
| `scripts/verify-tori-cursor.mjs` | 공통 원본 Git blob SHA 일치와 색상 외 override 금지 검증 |
| `app/layout.tsx` | 앱 전체 커서 연결 및 범용 병해충 메타데이터 |
| `app/components/FarmerDashboard.tsx` | 실제 집계를 카드와 필터 이동에 연결 |
| `tests/overview.test.tsx` | 모든 종류 노출, 고정 응애 요약 제거, 미연결 상태, 작업자 언어 검증 |

## 검증과 전달 상태

- 운영 현황 표시 검증 3개 통과: 실제 컴포넌트를 렌더링해 모든 catalog 종류가 펼침 조작 없이 보이는지, 비응애/복수 종류의 상단 요약, 미연결 시 비활성·미집계 표시, 4개 언어 이름을 확인했다. 실행 명령은 `npm run test:overview`다.
- `tsc --noEmit --incremental false`, `eslint . --ignore-pattern dist --ignore-pattern .next`, Sites build helper의 `vinext build`, `git diff --check` 통과.
- 앞선 API/권한/SQL 통합 검증 5개 결과는 [기능 작업 문서](PEST_AND_RECORD_WORKFLOWS.md)에 있다. 이번에는 서버 계약을 수정하지 않아 같은 통합 검증을 반복하지 않았다.
- 브라우저 시각 검수, 실제 포인터 동작, 모바일/E2E 검증은 수행하지 않았다. 빌드/마크업 통과를 시각 검수 완료로 취급하지 않는다.
- GitHub push는 이전 자동 승인 검토에서 원격 전송 및 branch 변경에 명시적 승인이 부족하다는 이유로 차단됐다. 원격 PR #2 head는 `3223b29`, 운영 Site는 version 22로 확인했다. 사용자 승인 전 push를 재시도하지 않으며 이번 변경도 운영 배포 완료로 취급하지 않는다.

## 후속 공통 원본 재사용 및 운영 반영

사용자가 운영 페이지 반영을 명시 요청하고, 공통 디자인은 색만 바꾸어 사용해야 한다고 재확인했다. 기존 농토리 전용 cursor TSX/CSS를 제거했다. GitHub에서 확인한 `conanbke-ai/Mystori_Project`의 `cc73e8ef14ec15804ce0b484ef76ac73e3345223` 공통 UI 컴포넌트와 스타일을 `vendor/tori-ui`로 고정해 그대로 소비한다. 별도 배포된 공통 패키지는 확인되지 않아 검증 가능한 원본 고정 방식을 사용했다. 다른 토리의 작업 파일은 변경하지 않았다.

- `npm run verify:cursor`: 원본 2개 파일 Git blob SHA 일치, 농토리 override가 색상 토큰만 사용하는지 통과.
- 변경 후 type, lint, Sites build helper, diff 검사 통과. 앞선 표시 3개/API 통합 5개 결과를 유지하며 브라우저/E2E를 추가 실행하지 않았다.
- 검증한 애플리케이션 소스는 `dd086273c45bb36546a765a080b197a8c06f4d29`다. 기존 Site 이력을 보존하는 배포 소스 `4ae40439b91ffc27952e839615f4fc83b87a7d85`와 Git tree가 동일함을 확인했다. 빌드를 재사용해 같은 Site에 저장·배포했다.
- Site version 23: `appgprj_6a8ffb7e18388191b8006cdc1a388b61~appgver_53097c4e55788191a76ef2cf7431ed33`.
- Deployment: `appgdep_6a9fcbe1af708191ac1941a2d6c8eac5`, 2026-09-08 08:48:45 UTC에 `succeeded`. 기존 소유자 전용 접근 범위를 유지했다.
- 운영 URL: https://seolhyang-mite-scout.conanbke.chatgpt.site
- 배포 후 읽기 전용 DB 조회에서 `capture_sessions.pest_code`가 존재함을 확인했다. 실농장 기록을 추가하거나 변경하지 않았다.
- GitHub CLI push는 이번에는 승인 차단이 아니라 로컬 쓰기 인증 부재로 실패했다. 기존 PR #2의 동일 branch를 연결된 GitHub 도구로 동기화하는 경로를 사용한다. 운영 Site 배포 성공과 GitHub branch 상태는 서로 구분한다.
