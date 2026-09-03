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

기존 딸기 프로젝트의 코드 기준본은 현재 연결된 GitHub 및 파일 라이브러리에서 확인되지 않아, 존재하지 않는 소스를 임의로 복원한 것처럼 취급하지 않습니다. 대신 확인 가능한 프로젝트 요구사항·데이터 수집 방향·디자인 산출물·개발 원칙을 이 저장소로 이관하고 이후 구현은 여기서 이어갑니다.

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

```text
CropAnalysisStrategy
├─ StrawberryStrategy
├─ TomatoStrategy        # 향후 확장
└─ PepperStrategy        # 향후 확장
```

딸기 내부에서도 숙도·등급·병해충·환경 스트레스 판단이 서로 독립적으로 교체될 수 있도록 구성합니다.

### Adapter

입력 출처가 달라져도 Domain은 동일한 데이터 계약만 보도록 합니다.

```text
ImageAdapter
ThermalAdapter
SensorAdapter
WeatherAdapter
ManualInputAdapter
DatasetAdapter
```

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

기존 코드를 패턴에 맞추기 위해 전면 재작성하지 않습니다. 수정하는 기능부터 점진적으로 새 구조에 맞춥니다.

## 데이터 원칙

- 실제 현장 데이터와 공개 데이터의 출처를 구분합니다.
- 이미지, 환경 수치, 라벨, 농장/구역 정보의 스키마를 명시적으로 관리합니다.
- Missing Data와 이상값을 모델 입력 전에 처리합니다.
- 관수 전/후, 정상/이상, 농가/환경 차이처럼 모델이 혼동할 수 있는 조건을 데이터셋에서 분리해 기록합니다.
- 모델 평가는 단순 Accuracy 하나가 아니라 클래스별 Precision/Recall/F1, confusion matrix, 현장 오탐/미탐을 함께 봅니다.
- 학습 데이터와 실제 사용자 업로드 데이터를 섞어 저장하지 않습니다.

상세 내용은 [`docs/DATA_STRATEGY.md`](docs/DATA_STRATEGY.md)를 참고합니다.

## UI / Mascot

농토리는 현장에서 빠르게 이해할 수 있는 시각적 인터페이스를 우선합니다.

- 큰 터치 영역과 명확한 상태 표현
- 한국어 우선, 향후 다국어 확장
- 긴 설명보다 상태 → 이유 → 권장 행동 순서
- 정상 / 주의 / 이상 징후를 색상과 아이콘으로 함께 구분
- 촬영 실패 시 기술 오류 대신 재촬영 행동을 직접 안내
- 마스코트는 정찰 토끼 콘셉트를 사용하며 분석·순찰·촬영·완료 상태를 시각적으로 보조

현재 복구 가능한 디자인 기준 자산은 `assets/design/`에 보존합니다.

## 환경 전략

```text
local
  ↓
simulation
  ↓
staging
  ↓
field / production
```

- **local**: 개발과 단위 테스트
- **simulation**: 공개/수집 데이터와 fixture를 통한 분석 검증
- **staging**: 실제 웹/API 흐름과 통합 테스트
- **field / production**: 실제 농장 환경에서 제한적으로 검증

포트폴리오 단계에서는 local/simulation/staging을 우선 완성하고, 실제 농가 테스트가 가능한 경우에만 field 단계로 확장합니다.

## 테스트 및 Quality Gate

기능 완료 시 최소 다음을 확인합니다.

```text
lint / format
→ unit test
→ data contract test
→ model/rule regression test
→ API test
→ UI smoke/E2E
→ build/deploy check
```

특히 다음은 회귀 테스트 우선 대상입니다.

- 입력 단위와 데이터 타입
- Missing Data / 이상값 처리
- 작물 Strategy 선택
- 숙도/등급 결과 계약
- 병해충 클래스 매핑
- 이미지와 환경 수치의 연결
- 분석 결과의 사용자별/세션별 분리
- 기존 작물에 새 작물 Strategy가 영향을 주지 않는지 여부

## 브랜치 규칙

```text
main                         항상 실행 가능한 기준본
feat/<scope>-<purpose>       기능 개발
fix/<scope>-<purpose>        버그 수정
refactor/<scope>-<purpose>   구조 개선
```

## 커밋 규칙

모든 개인 프로젝트와 동일하게 **1 기능 / 1 목적 / 1 커밋**을 기본으로 합니다.

```text
feat(scope): 기능 추가
fix(scope): 버그 수정
refactor(scope): 구조 개선
test(scope): 독립 테스트 보강
docs(scope): 문서 변경
style(scope): UI/CSS 표현 변경
chore(scope): 환경·설정·빌드 작업
```

Controller/Service/Repository/Frontend를 계층별로 의미 없이 쪼개지 않습니다. 하나의 사용자 기능을 완성하기 위한 변경은 하나의 기능 커밋으로 묶고, 별개의 리팩토링·버그·CI 변경은 분리합니다.

## 버전 전략

농토리는 앱 버전과 분석 자산 버전을 분리합니다.

```text
APP_VERSION
MODEL_VERSION
RULE_VERSION
DATA_SCHEMA_VERSION
```

예를 들어 모델만 교체됐을 때 앱 전체 버전만으로 결과 차이를 설명하지 않도록 합니다.

## Definition of Done

- [ ] 요구사항이 실제 사용자 흐름에서 동작한다.
- [ ] 입력 데이터 단위와 스키마가 검증된다.
- [ ] Sensor/Image/Weather 등 외부 입력이 Adapter를 통해 들어온다.
- [ ] 작물별 판단이 Strategy 또는 Domain 책임으로 분리되어 있다.
- [ ] Repository에 비즈니스 판단이 없다.
- [ ] Missing Data / 이상값 처리 경로가 있다.
- [ ] 기존 분석 결과 회귀 여부를 확인했다.
- [ ] 관련 자동 테스트를 추가하거나 갱신했다.
- [ ] UI 주요 흐름을 smoke/E2E로 확인했다.
- [ ] Secret·개인정보·원본 민감 데이터가 저장소에 포함되지 않았다.
- [ ] 필요한 문서를 갱신했다.
- [ ] 1 기능 / 1 목적 기준으로 커밋했다.

## 문서

- [Architecture](docs/ARCHITECTURE.md)
- [Project Scope](docs/PROJECT_SCOPE.md)
- [Data Strategy](docs/DATA_STRATEGY.md)
- [Design Guide](docs/DESIGN_GUIDE.md)
- [Development Standard](docs/DEVELOPMENT.md)
- [Migration Notes](docs/MIGRATION_NOTES.md)
