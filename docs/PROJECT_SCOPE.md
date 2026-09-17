# Project Scope

## 프로젝트 정의

농토리(Nongtori)는 기존 딸기 프로젝트에서 출발한 **데이터 기반 스마트팜 현장 지원 서비스**다. 첫 검증 작물은 딸기, 첫 중심 품종은 설향이지만 서비스·데이터·AI 구조는 특정 작물/품종에 종속시키지 않는다.

핵심 목표는 다음과 같다.

- 이미지·영상·환경·센서·수기 데이터를 일관된 계약으로 수집
- 과실 탐지, 숙도, 품질/등급, 병해충 분석을 현장 업무로 연결
- 반복적인 수확·선별 판단은 자동화하고 사람은 병해충 확인과 시스템 예외에 집중
- 데이터 수집 → 정규화 → 모델/규칙 → API → Farmer UI까지 포트폴리오에서 설명 가능한 구조 확보
- 향후 작물, 외부 기상, IoT, Robot 입력을 Adapter/Strategy 경계로 확장

중요 원칙:

> 포트폴리오 V1은 실제 제품 확장성을 설명할 수 있는 구조를 구현하되, 미래 스마트팜의 모든 자동화 기능을 지금 구현하지 않는다.

## 핵심 사용자

### 농민 / 농장 관리자
- 농장·공간구역별 상태 확인
- 수확/선별 판단 자동화
- 병해충 위험 구역 확인 및 필요 시 현장 검증
- 수확/판독/작업 기록 추적
- 실제 수확량과 시장가 기반 예상 정산 거래액 확인

### 현장 작업자
- 큰 터치 영역과 명확한 상태 표현
- 복잡한 전문용어 없이 촬영/확인/기록 수행
- 농장주와 판독 기록에 코멘트/답글 협업
- 향후 다국어 지원

### 포트폴리오 평가자
- 데이터 provenance와 leakage 방지
- 모델 baseline/Optuna/field validation
- Controller → Service → Repository / Domain / Infrastructure 책임 분리
- 실제 운영 UI와 AI 모델 연결 구조 확인
- 현재 구현 범위와 Future 자동화 범위가 명확히 분리되어 있는지 확인

## V1 범위

### 현장 데이터
- Google Sheet `딸기_프로젝트`를 working canonical source로 사용
- `컬럼정보`, `농가_딸기데이터`, `농가_베드길이` 탭
- 사진 데이터 정리는 진행 중이며 다른 사진/영상은 추가될 수 있음
- 학습은 live Sheet가 아니라 검증된 immutable snapshot만 사용

### 과실 분석
- Fruit Detection
- 동일 scan session 내 Tracking
- multi-frame Ripeness
- Harvest Decision
- Quality / Grade
- `FRESH / PROCESSING_JAM / REJECT` 용도 판단

`FULL = JAM` 같은 단순 규칙은 금지한다. 숙도 외에도 크기, 형태, 외관, 병징, 상품성을 함께 본다.

### 병해충
- 구조적으로 다종 확장 가능해야 하며 응애 단일 기능으로 고정하지 않는다.
- 첫 자동 예찰 개발 대상은 응애이며, 다른 병해충은 catalog/record 구조를 먼저 공유한다.
- 병해충은 `ALERT_AND_VERIFY` 정책을 사용하되 사람 입력이 inference의 필수 dependency가 되어서는 안 된다.
- 위험 CASE/의심구역은 자동 생성·병합·우선순위화한다.
- 농민/작업자가 아무 입력을 하지 않아도 다음 자동 관측과 위험도 계산은 계속 동작한다.
- `미입력/미확인`은 정상·음성 라벨로 변환하지 않는다.
- 현장 확인과 조치는 선택적 운영 evidence이며, 입력되면 case history와 향후 학습 데이터 품질 개선에 활용한다.
- UI는 `목록 → 구역/CASE 상세 → 필요 시 현장 확인/조치 기록` 흐름을 기본으로 한다.
- 목록에서는 내부 모델 용어보다 `습도 43%`, `주변보다 잎 온도 +1.8℃`, `반복 감지 3회`처럼 짧고 확인 가능한 관측 사실을 우선한다.
- 현장 확인 결과는 응애 확인/미확인 전용 enum으로 고정하지 않고 병해충/질병/기타 이상으로 확장 가능한 finding 구조를 사용한다.

### 공간 구조
- 모든 농가를 `동 → 베드 → 구역` 고정 계층으로 가정하지 않는다.
- canonical 위치는 `Farm → variable SpatialUnit hierarchy`다.
- `HOUSE`, `FACILITY`, `SECTION`, `BLOCK`, `BED`, `ROW`, `ZONE`, `CUSTOM` 등을 농가 구조에 맞게 선택적으로 사용한다.
- M처럼 동 단위 농가와 C1/C2처럼 대형 일체형 스마트팜을 같은 데이터 모델로 수용한다.
- 화면에서는 내부 계층 전체보다 농가가 실제 사용하는 location display code를 우선한다.

### Tracking
- V1 identity 범위는 동일 연속 영상/scan session
- ByteTrack baseline
- moving-camera 환경에서 BoT-SORT 비교
- custom persistent fruit ReID와 session 간 global fruit ID는 FUTURE

### 가격 / 예상 정산
- 품목/품종 코드 기반 범용 구조
- 첫 검증 대상: 딸기 설향
- 출력: 예상 낙찰단가(`KRW/kg`), 예상 정산 거래액
- 실제 농가 실정산 자료가 없으므로 `실제 실정산액`이라고 표현하지 않는다.
- `실제 수확량 × 예상 낙찰단가`로 예상 거래액을 계산한다.
- `source_harvest_date`와 `scenario_date`를 분리한다.

## 포트폴리오 V1 구현 우선순위

### MUST — 기한 내 실제 구현/검증 대상
- 현재 데이터 ingestion / provenance / snapshot 계약
- 과실 baseline + 숙도/품질/수확 판단의 설명 가능한 파이프라인
- 병해충 catalog와 응애 첫 예찰 Strategy
- 병해충 의심구역 목록/상세 화면
- CASE/history와 반복 알림 억제
- 환경/열화상 관측 근거의 간결한 표시
- 선택적 현장확인/조치 기록과 `UNKNOWN` 보존
- 가변 SpatialUnit을 수용할 수 있는 domain/API 설계
- 실제 앱/웹 주요 화면 visual acceptance

### SHOULD — 시간이 허용될 때
- 불규칙 반복 관측에서 이전 관측과의 변화량/경과시간 활용
- VPD/습도/열화상 환경 맥락 강화
- post-treatment 재감지/재발 이력 시각화
- 현장확인 데이터를 활용한 calibration/benchmark
- 실제 farm별/공간별 holdout 검증

### FUTURE — 설계만 열어두고 V1 구현 의무 없음
- 병해충 다종 AI 모델 전부 구현
- 작업자 자동배정/스케줄 최적화
- 로봇 경로 최적화/추가 촬영 waypoint 자동삽입
- 자동 방제기/방제 로봇 제어
- 완전자동 진단·처방
- 규칙적인 장기 시계열을 전제로 한 대형 sequence model

## 데이터 계약 핵심

- `Group_ID`: 동일 딸기의 다각도 관측 묶음이며 split atomic unit
- `F/RT45`: 시점 다양성 확보용. RT45는 실제 Robot camera placement 검증값이 아님
- `Length/Width/Weight_g`: ground truth
- `Grade=JM`의 일부 측정 NULL은 의도적 미측정일 수 있음
- `JM`과 `Health=MAL`은 동치가 아님
- 원본 `Farm` + `Zone` 및 원본 위치정보는 그대로 보존하고 내부 `Location Adapter`에서 `spatial_unit_id`로 정규화한다.
- `DataType=V`를 영상에 재사용

## V1 제외 / Future

- 실제 Robot navigation/SLAM 및 arm/gripper 제어
- session 간 persistent global fruit identity
- 미래 수확량 AI forecast를 V1 핵심 기능으로 승격
- RGB만으로 경도/당도/내부손상 확정
- 검증되지 않은 모든 병해충 완전자동 판정/방제
- 병해충 알림마다 농장주가 수동으로 담당자를 배정해야 하는 workflow
- 농민/작업자 입력을 강제하거나 미입력을 음성 라벨로 처리하는 workflow
- 실정산 이력이 없는 상태에서 개인화 실수령액 주장

## 성공 기준

1. 설계/데이터 계약이 코드보다 먼저 유지된다.
2. 동일 실제 개체와 연속 데이터가 split을 넘나들지 않는다.
3. 모델 acceptance가 임의 accuracy threshold가 아니라 baseline·operational metric·독립 test/field validation으로 결정된다.
4. 실패/외부 API 오류를 가짜 예측값으로 덮지 않는다.
5. 새 입력/작물/모델이 기존 UI·DB 전체 재작성으로 이어지지 않는다.
6. 실제 농업 현장에서 이해 가능한 상태 → 이유 → 행동 흐름을 제공한다.
7. Future 확장성을 위해 현재 V1의 완료 시점을 무기한 미루지 않는다.