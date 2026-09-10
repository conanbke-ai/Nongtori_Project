# Development Standard

## 구현 전 Documentation Gate

AI/data pipeline 구현은 `DESIGN_FREEZE_V1.md`와 관련 정책 문서가 canonical `main`에 반영되고 검증된 뒤에만 시작한다. 구조적 요구가 바뀌면 코드보다 문서를 먼저 수정하고 Design Review를 다시 연다.

필수 문서:

- `PROJECT_SCOPE.md`
- `ARCHITECTURE.md`
- `DATA_STRATEGY.md`
- `FIELD_DATA_CONTRACT.md`
- `AI_DECISION_POLICY.md`
- `DATA_SPLIT_POLICY.md`
- `FAILURE_EXCEPTION_POLICY.md`
- `MODEL_ACCEPTANCE_POLICY.md`
- `MARKET_PRICE_SETTLEMENT_POLICY.md`
- `AI_DATA_MODEL_SOURCES.md`
- `AI_DATA_PIPELINE_DESIGN.md`
- `DESIGN_FREEZE_V1.md`

## 작업 시작 순서

```text
Design Freeze 확인
→ 최신 main 확인
→ ACTIVE_WORK / open PR / branch budget 확인
→ 관련 코드/테스트/계약 확인
→ ALREADY_DONE / IN_PROGRESS / NEW / BLOCKED 판정
→ 변경 영향 범위 확인
→ Architecture Rule 확인
→ KEEP / MODIFY / REFACTOR / REPLACE / DELETE / CREATE / FUTURE 판정
→ 최소 리팩토링
→ 기능 구현
→ 테스트/회귀 검증
→ Source/Model/Decision 문서 갱신
→ Commit
```

## Architecture Rule

```text
Controller/API → Service → Domain → Repository Port → Infrastructure
```

- Controller가 Repository를 직접 호출하지 않는다.
- Service는 UI에 의존하지 않는다.
- Repository는 비즈니스/작물 판정을 하지 않는다.
- 외부 API/센서/파일/Sheet/모델/tracker/location 형식은 Adapter에서 처리한다.
- AI inference 결과와 농작업 Decision Policy를 분리한다.

## Pattern 우선순위

1. Strategy — 작물/분석 알고리즘
2. Adapter — 센서/기상/이미지/외부 데이터/모델/tracker/location
3. Repository — 저장/조회
4. Decision Policy — 병해충/숙도/등급/용도의 자동화 정책
5. Factory — Strategy/Analyzer 생성 분기 증가 시

## AI / Data 변경 규칙

외부 dataset/논문/model을 추가·교체할 때:

- `AI_DATA_MODEL_SOURCES.md` 갱신
- source lifecycle 상태 기록
- 원본 label 보존
- reported metric과 Nongtori reproduced/field metric 분리
- Optuna study/best params 기록
- raw dataset/weights를 Git에 무단 커밋하지 않음

## Refactoring Signal

- 동일 조건문 3곳 이상
- 동일 DB Query 2곳 이상
- Service 300~500 lines 초과
- 외부 data parsing과 판단 혼합
- 작물별 조건문 반복
- AI capability가 presentation에 하드코딩

## Branch / Workstream

기능마다 branch를 늘리지 않고 canonical workstream 단위로 제한한다. 기존 active lease와 겹치는 작업은 새 branch를 만들지 않고 기존 workstream에 합류한다. branch budget과 active workstream budget은 `ACTIVE_WORK.md`를 따른다.

## Commit

**1 기능 / 1 목적 / 1 커밋**을 기본으로 한다.

## Definition of Done

- 요구사항 완료
- Architecture/Decision Policy 위반 없음
- 데이터 계약 확인
- Missing/Invalid input 처리
- 관련 테스트 통과
- 회귀 확인
- 필요한 UI smoke/E2E/visual acceptance 확인
- Secret/민감 raw data 없음
- 외부 자료 Source Registry 갱신
- Model Card/metric/Optuna 결과 갱신
- NOT_RUN 항목 명시
- 문서 갱신
- 1 기능 / 1 목적 커밋
