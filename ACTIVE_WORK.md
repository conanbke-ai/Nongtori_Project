# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

| Workstream | Canonical branch / PR | 상태 | 주요 범위 | 주의 |
|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | theme/token, 모바일 접근성, cat jelly paw cursor contract, 초기 UI 구조 기준 | 이후 UI 구현은 main의 이 기준을 재사용한다. 같은 foundation branch를 다시 만들지 않는다. |

## 작업 시작 체크

1. `main` 실제 구현 확인
2. 이 파일 확인
3. open PR 검색
4. docs/설계와 기존 asset 확인
5. `ALREADY_DONE / IN_PROGRESS / NEW` 판정 후 수정

## Branch hygiene

동일한 농장/작업자/권한/다국어/UI 기능을 다른 대화창에서 다시 branch로 만들지 않는다. 기존 branch가 있으면 이어간다. 이미 main에 병합된 기반 기능은 재구현하지 않는다.

## 데이터 안전

Google Sheets/외부 원본 데이터는 기존 read-only 원칙을 유지하며, 새 세션에서 임의 더미/대체 데이터 구조를 다시 만들지 않는다.
