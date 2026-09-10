# 농토리 (Nongtori)

데이터 기반 작물 모니터링·환경 분석·농작업 지원을 위한 스마트팜 포트폴리오 프로젝트입니다.

> 기존의 **딸기 프로젝트**를 확장·정리한 후속 기준본입니다. 딸기를 첫 적용 작물로 사용하지만 서비스와 아키텍처는 특정 작물 하나에 종속되지 않도록 설계합니다.

## 프로젝트 목적

농토리는 고가의 전용 장비에 의존하기보다 현장에서 확보 가능한 이미지·환경 데이터·센서 또는 수기 입력을 조합해 농민과 현장 작업자가 빠르게 상태를 파악하도록 돕는 것을 목표로 합니다.

현재 핵심 범위는 다음과 같습니다.

- 작물 생육·품질 상태 분석
- 딸기 숙도 및 상품 등급 분류
- 병해충 이상 징후 예찰과 모니터링
- 농가 의견을 반영한 흰가루병 우선 대응 및 응애 조기 예찰
- RGB 이미지와 IR/열화상 데이터 활용 가능성 검토
- 환경 수치와 이미지의 멀티모달 분석
- 이상 징후 알림 및 분석 기록 관리
- 고령 농민과 외국인 현장 작업자를 고려한 단순하고 시각적인 UI
- 향후 딸기 외 작물로 확장 가능한 작물별 분석 전략

## 개발 기준 저장소

앞으로 농토리의 기능 개발, 리팩토링, 테스트, 문서화는 이 저장소 `Nongtori_Project`를 기준본으로 사용합니다.

구현 전에는 [`docs/DESIGN_FREEZE_V1.md`](docs/DESIGN_FREEZE_V1.md)의 상태와 Implementation Gate를 먼저 확인합니다. 2026-09-10 기준 V1 설계는 `DESIGN_FROZEN / DATA_WIP` 상태이며, Google Sheet 원본 데이터는 계속 정리될 수 있습니다.

## Architecture

농토리는 **데이터 입력 계층과 작물 판단 로직을 분리**하는 것을 가장 중요한 구조 원칙으로 둡니다.

```text
Sensor / Weather / Image / Manual Input
                  ↓
               Adapter
                  ↓
          Data Normalization
                  ↓
             Repository
                  ↓
              Domain
                  ↓
          Analysis Service
                  ↓
        Crop / Rule Strategy
                  ↓
                 API
                  ↓
              Farmer UI
```

### 공통 의존성 규칙

- UI는 DB나 모델을 직접 호출하지 않습니다.
- Controller/API는 요청 검증과 응답 변환을 담당하며 분석 규칙을 직접 구현하지 않습니다.
- Service는 분석 흐름을 조정하되 UI 코드에 의존하지 않습니다.
- Domain은 Flask/FastAPI, DB, 외부 API와 같은 기술 세부사항을 알지 않습니다.
- Repository는 저장/조회만 담당하며 작물 상태 판정을 하지 않습니다.
- 외부 센서·기상 API·파일·수기 입력은 Adapter에서 통일된 내부 데이터 구조로 변환합니다.
- 작물별 판단 차이는 조건문을 서비스 곳곳에 퍼뜨리지 않고 Strategy로 분리합니다.

상세 설계는 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)를 기준으로 합니다.

## 우선 적용 디자인 패턴

### Strategy — 최우선

작물이나 분석 목적별로 변경될 수 있는 판단 로직을 분리합니다.

### Adapter

입력 출처가 달라도 Domain은 동일한 데이터 계약만 보도록 합니다.

### Repository

분석 이력, 환경 관측값, 이미지 메타데이터, 모델 결과 등의 저장 기술을 비즈니스 로직과 분리합니다.

### Factory

작물 또는 분석 유형별 Strategy/Analyzer 생성 분기가 증가할 때 사용합니다. 단순 생성 한두 건에는 억지로 적용하지 않습니다.

## 리팩토링 기준

- 동일 조건문 3곳 이상 → Strategy 검토
- 동일 DB Query 2곳 이상 → Repository 이동 검토
- Service 약 300~500 lines 초과 → 책임 분리 검토
- 외부 API/센서 처리와 판단 로직이 섞임 → Adapter 분리
- 작물별 `if crop == ...` 분기가 반복됨 → Crop Strategy로 이동
- UI에서 백엔드 판단 규칙을 복제함 → 서버 규칙을 단일 기준으로 통합

## 데이터 원칙

- 실제 현장 데이터와 공개 데이터의 출처를 구분합니다.
- 이미지, 환경 수치, 라벨, 농장/구역 정보의 스키마를 명시적으로 관리합니다.
- 동일 `Group_ID`는 split을 넘지 않습니다.
- live Google Sheet를 직접 학습 입력으로 사용하지 않고 immutable snapshot을 사용합니다.
- Missing Data와 이상값을 모델 입력 전에 처리합니다.
- 모델 평가는 단순 Accuracy 하나가 아니라 task별 operational metric을 함께 봅니다.

## UI / Mascot

농토리는 현장에서 빠르게 이해할 수 있는 시각적 인터페이스를 우선합니다.

- 큰 터치 영역과 명확한 상태 표현
- 한국어 우선, 향후 다국어 확장
- 긴 설명보다 상태 → 이유 → 권장 행동 순서
- 정상 / 주의 / 이상 징후를 색상과 아이콘으로 함께 구분

## 테스트 및 Quality Gate

```text
lint / format
→ unit test
→ data contract test
→ model/rule regression test
→ API test
→ UI smoke/E2E
→ build/deploy check
```

## 브랜치 / 커밋

- `main`: canonical baseline
- 기능별 새 branch 남발 금지, `ACTIVE_WORK.md`의 branch budget과 canonical workstream 준수
- **1 기능 / 1 목적 / 1 커밋**을 기본으로 함

## 문서

- [Design Freeze v1](docs/DESIGN_FREEZE_V1.md)
- [Project Scope](docs/PROJECT_SCOPE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data Strategy](docs/DATA_STRATEGY.md)
- [Field Data Contract](docs/FIELD_DATA_CONTRACT.md)
- [AI Decision Policy](docs/AI_DECISION_POLICY.md)
- [Data Split & Leakage Policy](docs/DATA_SPLIT_POLICY.md)
- [Failure & Exception Policy](docs/FAILURE_EXCEPTION_POLICY.md)
- [Model Acceptance Policy](docs/MODEL_ACCEPTANCE_POLICY.md)
- [Market Price & Settlement Policy](docs/MARKET_PRICE_SETTLEMENT_POLICY.md)
- [AI / Data / Model Sources](docs/AI_DATA_MODEL_SOURCES.md)
- [AI Data Pipeline Design](docs/AI_DATA_PIPELINE_DESIGN.md)
- [Design Guide](docs/DESIGN_GUIDE.md)
- [Development Standard](docs/DEVELOPMENT.md)
- [Migration Notes](docs/MIGRATION_NOTES.md)
