# Architecture

## 1. 목표

농토리의 핵심은 특정 딸기 모델 하나를 서비스에 박아 넣는 것이 아니라, **여러 입력 소스와 여러 작물/분석 규칙을 교체할 수 있는 구조**를 만드는 것입니다.

아키텍처는 다음 두 가지를 최우선으로 보호합니다.

1. 외부 입력 방식이 바뀌어도 분석 로직이 흔들리지 않을 것
2. 새로운 작물/분석 규칙이 추가되어도 기존 작물 코드 수정이 최소화될 것

## 2. 전체 구조

```text
[Input Sources]
Sensor / Weather / RGB / Thermal / Manual / Dataset
                     ↓
                 Adapters
                     ↓
              Normalization
                     ↓
                Repository
                     ↓
                  Domain
                     ↓
            Analysis Services
                     ↓
         Crop / Analysis Strategy
                     ↓
               API / DTO
                     ↓
                 Web UI
```

## 3. 계층별 책임

### Controller / API

- HTTP 요청 파싱
- 입력값 기본 검증
- 인증/세션 확인
- Service 호출
- DTO 응답 변환

금지:

- 모델 직접 실행
- DB 직접 조회
- 작물 판정 조건문 구현

### Application Service

- 한 유스케이스의 처리 순서 조정
- 필요한 Adapter/Repository/Strategy 호출
- 트랜잭션 또는 분석 세션 경계 관리

금지:

- HTML/CSS/DOM 의존
- 특정 DB SQL 직접 작성
- 외부 API 응답 구조에 직접 의존

### Domain

후보 도메인:

```text
Crop
Observation
Environment
Irrigation
Growth
Quality
Disease
Pest
Harvest
Alert
AnalysisResult
```

Domain은 Flask, DB, Kaggle, 기상 API 같은 기술 이름을 몰라야 합니다.

### Repository

저장/조회 책임:

- Observation
- Image metadata
- Environment sample
- Analysis result
- Model run metadata
- Alert history

Repository는 `이 값이면 응애 의심`, `숙도 4단계` 같은 판정을 하지 않습니다.

### Infrastructure / Adapter

외부 세계의 데이터를 내부 계약으로 변환합니다.

```text
RgbImageAdapter
ThermalImageAdapter
SensorAdapter
WeatherAdapter
ManualInputAdapter
DatasetAdapter
NotificationAdapter
```

### Strategy

작물별/분석별 변경 지점을 Strategy로 둡니다.

예시:

```text
CropAnalysisStrategy
└─ StrawberryStrategy

DiseaseAnalysisStrategy
├─ PowderyMildewStrategy
└─ SpiderMiteStrategy

QualityStrategy
├─ RipenessStrategy
└─ GradeStrategy
```

초기에는 클래스 수를 억지로 늘리지 않습니다. 동일 조건 분기나 알고리즘 교체 필요성이 실제로 생기는 시점에 분리합니다.

## 4. 의존성 규칙

```text
UI → API → Service → Domain/Port
                       ↓
                 Infrastructure
```

- UI → Repository 직접 접근 금지
- Controller → Repository 직접 접근 금지
- Repository → Domain 판정 금지
- Domain → Framework/DB/API 의존 금지
- Strategy → UI 의존 금지

## 5. 리팩토링 신호

- 동일 조건문 3곳 이상 → Strategy 검토
- 동일 Query 2곳 이상 → Repository 검토
- Service 300~500 lines 이상 → 책임 분리
- 입력 소스별 파싱 코드가 Service에 등장 → Adapter 이동
- `if crop == ...` 반복 → Crop Strategy 이동
- 결과 DTO마다 동일한 변환 코드 반복 → Mapper/Assembler 검토
- 모델 로딩/추론/후처리가 한 함수에 섞임 → Inference Pipeline 분리

## 6. 데이터 처리 파이프라인

```text
Raw Input
→ Validate
→ Normalize
→ Feature/Preprocess
→ Analyze / Infer
→ Postprocess
→ Domain Result
→ Persist
→ Present / Alert
```

각 단계의 입출력 스키마를 테스트 가능하게 유지합니다.

## 7. 모델 계층

모델 자체는 Domain이 아니라 Infrastructure 성격의 구현체로 봅니다.

```text
Analysis Port
   ↑
Model Adapter
   ├─ CNN / ViT
   ├─ YOLO
   ├─ Classical ML
   └─ Rule-based fallback
```

Service/Domain은 모델 파일명이나 PyTorch/TensorFlow 구현을 직접 알지 않습니다.

## 8. 환경 전략

```text
local → simulation → staging → field/production
```

### local
- 빠른 개발
- fixture
- 단위 테스트

### simulation
- 공개 데이터/가공 데이터
- 데이터 계약 검증
- 모델/규칙 회귀 테스트

### staging
- 실제 API/UI
- 파일 업로드
- DB
- 알림 연동 테스트

### field/production
- 실제 농장 환경
- 제한된 사용자
- 오탐/미탐 기록
- 운영 로그

## 9. 점진적 마이그레이션

기존 딸기 프로젝트 코드가 다시 확보되더라도 폴더 전체를 즉시 재작성하지 않습니다.

```text
기존 기능 확인
→ 테스트 가능 여부 확인
→ 책임/의존성 위반 식별
→ 필요한 최소 분리
→ 기존 동작 보존 테스트
→ 새 구조에 편입
```

새 구현은 처음부터 이 문서의 의존성 방향을 따릅니다.
