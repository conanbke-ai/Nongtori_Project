# Development Standard

## 작업 시작 순서

모든 구현 요청은 다음 순서로 처리합니다.

```text
현재 main 기준본 확인
→ 관련 코드/테스트 확인
→ 변경 영향 범위 확인
→ Architecture Rule 확인
→ 필요한 Pattern 판단
→ 최소 리팩토링
→ 기능 구현
→ 테스트/회귀 검증
→ 문서 갱신
→ Commit
```

## Architecture Rule

```text
Controller/API → Service → Domain → Repository Port → Infrastructure
```

- Controller가 Repository를 직접 호출하지 않습니다.
- Service가 UI에 의존하지 않습니다.
- Repository가 작물 판정을 하지 않습니다.
- 외부 API/센서/파일 형식은 Adapter에서 처리합니다.

## Pattern 우선순위

1. Strategy — 작물/분석 알고리즘
2. Adapter — 센서/기상/이미지/외부 데이터
3. Repository — 저장/조회
4. Factory — Strategy/Analyzer 생성 분기 증가 시

## Refactoring Signal

- 동일 조건문 3곳 이상
- 동일 DB Query 2곳 이상
- Service 300~500 lines 초과
- 외부 데이터 파싱과 판단이 한 함수에 혼합
- 작물별 조건문 반복

## Branch

```text
main
feat/<scope>-<purpose>
fix/<scope>-<purpose>
refactor/<scope>-<purpose>
```

## Commit

**1 기능 / 1 목적 / 1 커밋**

```text
feat(scope): ...
fix(scope): ...
refactor(scope): ...
test(scope): ...
docs(scope): ...
style(scope): ...
chore(scope): ...
```

같은 사용자 기능을 완성하는 API/Service/UI/Test 변경은 하나의 기능 커밋으로 묶을 수 있습니다. 독립적인 리팩토링이나 별도 버그는 분리합니다.

## Definition of Done

- 요구사항 완료
- Architecture 위반 없음
- 데이터 계약 확인
- Missing/Invalid input 처리
- 관련 테스트 통과
- 기존 결과 회귀 확인
- UI smoke 확인
- Secret/민감 데이터 없음
- 문서 갱신
- 1 기능 / 1 목적 커밋
