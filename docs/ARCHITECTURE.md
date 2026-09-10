# Architecture

## 1. 목표

농토리는 특정 딸기 모델을 서비스에 박아 넣는 구조가 아니라 **입력 소스·작물·분석 모델·의사결정 정책을 교체할 수 있는 구조**를 사용한다.

보호할 원칙:

1. 입력 방식이 바뀌어도 Domain/분석 규칙이 흔들리지 않는다.
2. 새 작물/분석 규칙이 추가되어도 기존 코드 수정이 최소화된다.
3. AI 결과와 실제 농작업 의사결정 정책을 분리한다.
4. 현재 수기 위치/영상 방식과 미래 Robot 연계를 Adapter 경계로 분리한다.

## 2. 전체 구조

```text
Sensor / Weather / RGB / Thermal / Manual / Dataset / Video
                          ↓
                       Adapter
                          ↓
                    Normalization
                          ↓
                     Repository
                          ↓
                       Domain
                          ↓
                  Analysis Service
                          ↓
              Strategy / Decision Policy
                          ↓
                      API / DTO
                          ↓
               Farmer UI / Future Robot Adapter
```

## 3. 계층 책임

### Controller / API
- HTTP 요청/기본 validation
- 인증·권한·세션
- Service 호출
- DTO 응답 변환

금지: 모델 직접 실행, DB 직접 조회, 작물 판정 규칙 구현.

### Service
- use case 처리 순서
- Adapter/Repository/Strategy 호출
- 분석 세션·tracking 결과 조합

금지: UI 의존, SQL 직접 작성, 외부 API 응답 구조 직접 의존.

### Domain

후보:

`Crop`, `Observation`, `Environment`, `Growth`, `Quality`, `Disease`, `Pest`, `Harvest`, `Alert`, `AnalysisResult`, `FruitTrack`, `RipenessResult`, `QualityResult`, `UsageDecision`, `LocationContext`, `MarketPriceObservation`, `PriceForecastResult`, `SettlementEstimateResult`.

Domain은 framework, DB, model filename, 외부 API를 모른다.

### Repository

저장/조회만 담당한다. `응애 의심`, `수확 적기`, `JM`, `JAM` 같은 비즈니스 판단은 금지한다.

### Infrastructure / Adapter

- `RgbImageAdapter`
- `ThermalImageAdapter`
- `SensorAdapter`
- `WeatherAdapter`
- `ManualInputAdapter`
- `FieldSpreadsheetAdapter`
- `DatasetAdapter`
- `ModelInferenceAdapter`
- `TrackerAdapter`
- `LocationContextProvider`
- `NotificationAdapter`
- `MarketDataAdapter`
- `RobotAdapter` (Future)

## 4. AI / Tracking pipeline

```text
Video Frame
→ Fruit Detector
→ Tracker Adapter
→ Fruit Track
→ Ripeness / Quality Analysis
→ Track-level Temporal Aggregation
→ Decision Policy
```

V1은 ByteTrack baseline과 BoT-SORT를 동일 video set에서 비교한다. identity 보장 범위는 동일 연속 영상/scan session이다. session 간 persistent global fruit ID와 custom fruit ReID는 Future다.

## 5. Decision Policy

분석 결과와 자동화 정책을 분리한다.

```text
Pest result → ALERT_AND_VERIFY → VERIFY_ZONE
Ripeness/Grade/Usage → AUTO_DECIDE
System/Data/Model failure → SYSTEM_EXCEPTION
```

상세 정책은 `AI_DECISION_POLICY.md`를 따른다.

## 6. 위치 context

현재:

```text
FIELD_MANUAL_LABEL + optional VIDEO_PIPE_ANCHOR
→ LocationContext
```

미래:

```text
Robot Navigation / Localization
→ RobotLocationAdapter
→ LocationContext
```

원본 `Farm`/`Zone`을 source field로 보존하고 derived house/bed/zone은 별도 관리한다. 철파이프는 농가 공통 거리 규칙이 아니라 구역 내부 relative anchor다.

## 7. Data pipeline architecture

```text
Google Sheet (WORKING SOURCE)       External Dataset Providers
          ↓ FieldSpreadsheetAdapter          ↓ Provider Adapters
          └──────────────────┬────────────────┘
                             ↓
                       Data Audit
                             ↓
                       Normalization
                             ↓
                    Dataset Manifest
                             ↓
                  Immutable Snapshot
                             ↓
                 Split / Train / Evaluate
```

live Sheet와 raw external dataset을 직접 학습 입력으로 사용하지 않는다.

## 8. Market price / settlement

```text
Official Market API
→ MarketDataAdapter
→ MarketPriceNormalizer
→ MarketPriceRepository
→ PriceForecastService → PriceModelPort
→ SettlementEstimator
→ API / Farmer UI
```

원본 단위/포장 정보를 보존한 뒤 `KRW/kg`로 정규화한다. 예측 input cutoff와 actual market reference를 분리해 leakage를 막는다.

## 9. 의존성 규칙

```text
UI → API → Service → Domain/Port
                       ↓
                 Infrastructure
```

- UI → Repository 직접 접근 금지
- Controller → Repository 직접 접근 금지
- Repository → 비즈니스/작물 판정 금지
- Domain → Framework/DB/API 의존 금지
- Strategy/Decision Policy → UI 의존 금지
- model weight/framework → Infrastructure

## 10. 리팩토링 신호

- 동일 조건문 3곳 이상 → Strategy/Decision Policy
- 동일 Query 2곳 이상 → Repository
- Service 300~500 lines 초과 → 책임 분리
- 외부 파싱+판단 혼합 → Adapter 분리
- 작물별 `if crop` 반복 → Crop Strategy
- AI 지원 여부가 UI에 하드코딩 → Capability Registry
- 모델 loading/inference/postprocess 혼합 → Inference Pipeline

## 11. 환경

```text
local → simulation → staging → field/production
```

새 구조는 변경 기능부터 점진적으로 적용하며 전체 재작성을 금지한다.
