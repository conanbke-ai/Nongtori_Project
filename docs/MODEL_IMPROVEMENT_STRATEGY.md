# Nongtori Model Improvement Strategy

Status: **CANONICAL / REQUIRED**

이 문서는 Nongtori에서 사용하는 각 모델/용도별로 **무엇이 문제일 때 무엇을 조정해야 하는지**, 그리고 **어떤 metric으로 개선 여부를 판단해야 하는지**를 구분한다.

공통 원칙은 단순하다.

```text
Observed Problem
→ Root-cause Hypothesis
→ Small Controlled Change
→ Validation Result
→ Delta vs Baseline
→ Keep / Reject / Retest
→ Next Experiment
```

모든 모델을 같은 방식으로 개선하지 않는다. 문제 유형, 비용 구조, 운영 리스크가 다르므로 모델별 개선 레버와 acceptance metric을 분리한다.

---

# 1. Task Registry

| 영역 | 문제 유형 | 대표 모델군 | Primary Metric | 핵심 운영 리스크 |
|---|---|---|---|---|
| 숙도 판정 | Ordinal Classification | ResNet / EfficientNet / ConvNeXt | Macro F1, Ordinal MAE, Weighted Kappa | 인접 숙도 경계 혼동 |
| 병해충 판독 | Detection / Classification | YOLO 계열 / CNN·ViT | Recall, Precision, F1, PR-AUC | 미탐 및 과도한 false alert |
| 과실/잎 객체 탐지 | Object Detection | YOLO 계열 | mAP50-95, Recall | 작은 객체·가림·bbox 누락 |
| Tracking / 개체 수 집계 | Multi-object Tracking | ByteTrack / BoT-SORT | IDF1, HOTA, Count Error | ID Switch, 중복 카운트 |
| 가격 예측 | Time-series Regression | XGBoost / LightGBM / LSTM 계열 | MAE, RMSE, R², WAPE | 시계열 leakage, 급등락 대응 |
| 성장량/크기 예측 | Regression | Tree / MLP / Sequence model | MAE, RMSE, R² | 표본 편향, 측정오차 |

---

# 2. Ripeness / Maturity Model

## 목적

과실 crop을 입력으로 받아 숙도 단계를 판정한다. Nongtori 숙도는 순서가 존재하므로 일반 다중분류보다 **ordinal error**가 중요하다.

## 대표 실패 유형

1. 인접 stage 혼동 (`M0 ↔ M1`, 향후 `M1 ↔ M2` 등)
2. 특정 stage F1 저하
3. train loss는 계속 감소하지만 valid metric 저하
4. best epoch가 지나치게 빠름
5. 특정 source/domain에서만 성능이 좋음

## 원인별 개선 우선순위

### A. Optimization 문제

증상:
- best epoch가 1~2에 발생
- train loss는 감소하지만 valid Macro F1이 악화

우선 조정:
1. learning rate 축소
2. backbone freeze + head warm-up
3. gradual unfreeze
4. discriminative LR
5. scheduler

모델 교체보다 먼저 optimization을 안정화한다.

### B. 인접 숙도 경계 혼동

증상:
- confusion matrix에서 adjacent class 방향 오류 집중
- 전체 accuracy는 높지만 특정 stage precision/recall 낮음

우선 조정:
1. 데이터/label boundary 재검토
2. class별 augmentation 점검
3. label smoothing
4. focal loss 또는 ordinal-aware loss 검토
5. 더 강한 backbone 비교

### C. 데이터 범위 부족

증상:
- 특정 maturity가 아예 없거나 너무 적음
- external domain만 존재

대응:
- 모델 튜닝으로 해결했다고 주장하지 않는다.
- 새로운 field snapshot / calibration data 확보가 우선이다.

## Improvement ladder

```text
LR tuning
→ staged fine tuning
→ scheduler
→ loss adjustment
→ backbone comparison
→ Optuna
→ frozen test
→ field validation
```

## 평가 metric

- Macro F1
- class별 Precision / Recall / F1
- Ordinal MAE
- Weighted Kappa
- Confusion Matrix
- train / valid loss divergence
- best epoch / early-stop epoch

## 현재 baseline

`RIPENESS-BASELINE-V001`

- Test Macro F1: 0.9402
- M1 F1: 0.9023
- Ordinal MAE: 0.0901
- Weighted Kappa: 0.9420
- 주요 failure: `M0 → M1`
- best epoch: 1

세부 실험 이력은 `docs/RIPENESS_MODEL_IMPROVEMENT_LOG.md`에서 관리한다.

---

# 3. Pest / Disease Model

병해충 모델은 단순 accuracy보다 **미탐 비용과 과도한 현장 알림 비용**이 중요하다.

## 대표 실패 유형

1. 병해충이 있는데 탐지하지 못함
2. 정상 잎/반사/흙/그림자를 병해충로 오탐
3. 특정 농가/조명에서 오탐 급증
4. 작은 병반/응애 등 소형 target recall 부족
5. 클래스 불균형으로 희귀 병해충 recall 저하

## 개선 순서

### A. 미탐이 많은 경우

우선 검토:
1. annotation 누락 확인
2. image resolution 증가
3. small-object augmentation
4. confidence threshold 조정
5. positive sample 보강
6. model scale / backbone 강화

### B. 오탐이 많은 경우

우선 검토:
1. hard-negative sample 추가
2. background 다양성 확대
3. class definition 충돌 확인
4. confidence / NMS threshold 조정
5. false-positive mining

### C. 특정 농가/domain에서 무너지는 경우

- farm/source별 metric 분리
- color/illumination augmentation
- domain-specific validation set
- 필요 시 fine-tuning snapshot 분리

## 평가 metric

- Recall
- Precision
- Macro / per-class F1
- PR-AUC
- false alerts / zone
- missed positive count

병해충은 운영상 Recall을 중요하게 보되, false alert가 지나치게 증가하면 채택하지 않는다.

---

# 4. Fruit / Leaf Object Detection

## 대표 실패 유형

1. 작은 과실 누락
2. 잎 뒤 가려진 과실 누락
3. bbox가 지나치게 크거나 작음
4. 동일 과실 중복 detection
5. fruit / flower / leaf class confusion

## 개선 순서

### 데이터 품질 먼저

1. bbox annotation QA
2. class mapping 오류 확인
3. 누락 bbox 샘플 audit
4. small / occluded subset 별도 평가

### 모델/학습 조정

1. input resolution
2. scale/crop augmentation
3. class balance
4. confidence/NMS tuning
5. model size 비교
6. 필요 시 task-specific augmentation

## 평가 metric

- mAP50
- mAP50-95
- Precision
- Recall
- small-object recall
- occluded-object recall
- duplicate detection rate

전체 mAP 하나만 좋아지고 small/occluded recall이 나빠지면 실제 농장 적용 후보로 올리지 않는다.

---

# 5. Tracking / Unique Fruit Counting

Detection과 Tracking을 하나의 성능으로 취급하지 않는다.

Detection이 좋아도 tracking association이 불안정하면 개체 수 집계는 틀릴 수 있다.

## 대표 실패 유형

1. 같은 딸기의 ID가 계속 바뀜
2. 화면 재진입 시 신규 개체로 중복 카운트
3. 잠깐 가려졌다가 다시 등장할 때 ID 소실
4. detector confidence가 낮아 track fragmentation 발생
5. tracker를 보수적으로 설정해 실제 개체가 합쳐짐

## 개선 레버

1. detector confidence threshold
2. tracker high/low threshold
3. track buffer
4. association IoU threshold
5. ReID 사용 여부
6. ByteTrack vs BoT-SORT 비교
7. frame rate / sampling interval

## 평가 metric

- IDF1
- HOTA
- ID Switch
- Fragmentation
- Unique Fruit Count Error
- Duplicate Count
- Missed Unique Fruits
- FPS
- VRAM / CPU cost

## 채택 기준

최종 tracker는 accuracy만이 아니라:

```text
Tracking stability
+ Count accuracy
+ Runtime cost
```

세 가지 trade-off로 결정한다.

---

# 6. Price Forecast Model

가격 예측은 이미지 모델과 개선 방법이 완전히 다르다.

## 가장 먼저 확인할 것

1. chronological split인지
2. 미래 정보 leakage가 없는지
3. target horizon이 명확한지
4. lag / rolling feature가 예측 시점에 실제 사용 가능한 값인지

Leakage가 있는 높은 R²는 성능으로 인정하지 않는다.

## 대표 실패 유형

### A. 전체 추세는 맞는데 급등락을 놓침

검토:
- lag window
- rolling volatility
- 계절성
- 공휴일/출하량/기상 feature
- objective / loss

### B. 특정 시기만 크게 틀림

검토:
- regime shift
- seasonal segmentation
- rolling validation
- external event feature

### C. R²는 높은데 실제 가격 오차가 큼

R²만 사용하지 않는다.

반드시:
- MAE
- RMSE
- sMAPE 또는 WAPE
- 예상 거래액 오차

를 함께 본다.

## 개선 순서

```text
Leakage audit
→ Baseline naive forecast
→ Feature engineering
→ Tree model tuning
→ Sequence model comparison
→ Ensemble / hybrid
→ chronological holdout
```

## 모델 비교

- Naive / seasonal naive
- XGBoost / LightGBM
- LSTM/GRU 계열은 데이터량과 시계열 dependency가 충분할 때 비교

복잡한 모델이 단순 tree baseline보다 의미 있게 개선되지 않으면 채택하지 않는다.

---

# 7. Growth / Size Regression

길이, 폭, 중량, 생육량 등의 연속형 예측에 사용한다.

## 대표 실패 유형

1. 큰 개체/작은 개체에서 편향
2. 특정 농가 데이터에 과적합
3. 측정값 noise가 큼
4. 평균값 근처로만 예측

## 개선 순서

1. 측정 데이터 QA
2. outlier / missing policy 확인
3. farm/source stratification
4. feature scaling / feature selection
5. loss 비교 (MSE / MAE / Huber)
6. tree vs neural model 비교

## 평가 metric

- R²
- MAE
- RMSE
- residual distribution
- size-range별 MAE
- farm/source별 MAE

전체 R²만 좋고 특정 농가 residual bias가 크면 운영 모델로 채택하지 않는다.

---

# 8. 공통 Experiment Decision Matrix

모든 실험은 변경 이유를 아래 category 중 하나로 명시한다.

| Category | 의미 | 대표 조정 |
|---|---|---|
| DATA | 데이터 자체 문제 | 추가 수집, label QA, balance |
| PREPROCESS | 입력 표현 문제 | crop, resize, normalization |
| OPTIMIZATION | 학습 불안정 | LR, optimizer, scheduler, freeze |
| LOSS | 오류 비용 반영 문제 | class weight, focal, smoothing |
| ARCHITECTURE | 모델 표현력 한계 | backbone/model family 변경 |
| THRESHOLD | inference decision 문제 | confidence/NMS/tracker threshold |
| TEMPORAL | 시계열 구조 문제 | lag/window/horizon |
| DOMAIN | 농가/환경 일반화 문제 | domain augmentation, field FT |

실험 문서에는 반드시 `Change Category`를 기록한다.

---

# 9. Model-specific Experiment Record

모든 모델 실험은 아래 형식을 사용한다.

```markdown
## EXP-XXX — <experiment name>

### Task
- ripeness / pest / detection / tracking / price / growth

### Change Category
- DATA / PREPROCESS / OPTIMIZATION / LOSS / ARCHITECTURE / THRESHOLD / TEMPORAL / DOMAIN

### Baseline
- model:
- snapshot:
- primary metrics:

### Observed Problem

### Root-cause Hypothesis

### Change Applied

### Why This Change Fits This Task

### Controlled Variables

### Validation Result

### Delta vs Baseline

### Failure Pattern After Change

### Runtime / Resource Change

### Decision
- KEEP / REJECT / RETEST / PROMOTE_CANDIDATE

### Next Action
```

`Why This Change Fits This Task`를 반드시 남겨서, 예를 들어 숙도 모델에서 LR을 조정한 이유와 가격 예측에서 lag feature를 조정한 이유가 같은 '튜닝'으로 뭉개지지 않게 한다.

---

# 10. 최종 모델 선택 원칙

Nongtori에서는 "가장 높은 단일 점수"가 최종 모델을 의미하지 않는다.

최종 선택은 각 task에 맞춰:

```text
Accuracy / Error
+ Failure pattern
+ Generalization
+ Runtime / resource cost
+ Operational risk
```

를 함께 판단한다.

예:

- 숙도: Macro F1이 조금 높아도 M1 boundary failure가 심하면 탈락
- 병해충: Precision이 높아도 recall이 낮아 미탐이 많으면 탈락
- Tracking: IDF1이 좋아도 count error가 크면 탈락
- 가격 예측: R²가 높아도 leakage가 있거나 MAE가 크면 탈락

이 원칙을 통해 모델 개선 과정과 모델 선택 이유를 포트폴리오/운영 문서에서 명확하게 설명할 수 있어야 한다.
