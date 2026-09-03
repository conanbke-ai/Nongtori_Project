# Data Strategy

## 1. 핵심 원칙

농토리의 모델 품질은 모델 구조보다 **현장 조건이 제대로 라벨링된 데이터**에 더 크게 좌우된다고 봅니다.

따라서 이미지 파일만 모으지 않고 아래 메타데이터를 함께 관리합니다.

- 작물/품종
- 농가/구역
- 촬영 일시
- RGB/IR/열화상 여부
- 정상/이상 라벨
- 병해충 종류
- 숙도/등급
- 관수 전/후
- 온도/습도 등 환경값
- 촬영 거리/각도/광량 조건
- 라벨 검수 상태

## 2. 초기 딸기 데이터 시나리오

### CASE 1. 생육/품질
- 숙도 단계
- 상품 등급
- 외관 이상

### CASE 2. 병해충/스트레스
- 흰가루병
- 응애
- 정상 잎
- 관수/습윤 상태

응애와 물에 젖은 잎을 혼동하지 않도록 관수 전/후 데이터를 별도로 확보하고 기록합니다.

## 3. RGB + Thermal/IR

RGB와 열화상은 같은 샘플을 동일 ID로 연결할 수 있도록 합니다.

```text
observation_id
├─ rgb_image
├─ thermal_image
├─ environment
└─ labels
```

열화상 단독으로 병해충을 확정하지 않고, 환경 수치와 RGB 특징을 함께 비교하는 방향을 우선합니다.

## 4. 데이터셋 분리

- train
- validation
- test
- field holdout

같은 농가/같은 연속 촬영 프레임이 train과 test에 섞여 과대평가되지 않도록 농가·구역·촬영 세션 단위 분리를 검토합니다.

## 5. 이상값 / Missing Data

- 센서 단위 검증
- 물리적으로 불가능한 범위 차단
- 누락값 명시
- 임의 0 대입 금지
- 모델이 요구하는 필드와 선택 필드 분리

## 6. 평가 지표

분류 모델:
- Precision
- Recall
- F1
- confusion matrix
- class별 support

탐지 모델:
- mAP
- Precision / Recall
- 현장 false positive / false negative

농업 현장에서는 이상 징후를 놓치는 미탐 비용과 과도한 오탐 비용이 다르므로 클래스별 임계값을 별도 검토합니다.

## 7. 데이터 버전

```text
DATA_SCHEMA_VERSION
DATASET_VERSION
LABEL_POLICY_VERSION
```

모델 버전과 데이터 버전을 별도로 기록해 같은 모델 코드라도 학습 데이터 변화로 결과가 달라진 이유를 추적할 수 있게 합니다.
