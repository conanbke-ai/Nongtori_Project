# Nongtori External Ripeness / Weight Audit V1

Status: **CANONICAL CANDIDATE / EXTERNAL-DATA-ONLY**

Checked: 2026-09-17

## 1. 목적

현장 사진·영상 정리가 완료되기 전까지 외부 공개 데이터만으로 진행 가능한 작업을 분리한다.

현재 우선순위는 다음 두 축이다.

1. `Ripeness / Maturity 0~4` 외부데이터 확장과 source compatibility audit
2. `Grade`를 직접 이미지 분류하지 않고 `Weight estimation + quality override`로 구성하기 위한 외부데이터 audit

현장 원본은 이 문서의 학습 입력 범위에 포함하지 않는다.

## 2. Nongtori Grade 정책 재확인

Google Sheet `딸기_프로젝트 / 컬럼정보`의 field rule을 canonical 기준으로 사용한다.

```text
SP = 특상 / 22g 이상
HI = 상   / 16g 이상
MD = 중   / 12g 이상
JM = 하 / 기형과
NA = 미수확
```

따라서 Grade의 기본 구조는 image-to-grade black-box classifier가 아니다.

```text
Fruit Detection / Tracking
→ Weight Estimation
→ Weight Grade
→ Quality Override
→ Final Grade
```

기본 weight grade:

```text
weight >= 22g → SP
weight >= 16g → HI
weight >= 12g → MD
weight <  12g → JM candidate
```

Quality override:

```text
Health=MAL / malformed → JM
overripe / severe sellability defect → JM candidate according to versioned policy
```

금지:

```text
외부 A/B/C/Jumbo label → SP/HI/MD/JM 직접 치환
Maturity=4 → JM
JM → MAL
JM → PROCESSING_JAM
```

`estimated_weight_g`, `weight_grade`, `quality_override`, `grade_reason`, `final_grade`는 서로 분리한다.

## 3. DATA-RIP-002 / KGCV 재평가

Source:
- HF mirror: `Project-AgML/strawberry_growth_detection`
- Original dataset DOI: `10.5281/zenodo.10957909`
- License recorded in current registry: CC BY 4.0

### 3.1 HF mirror에서 즉시 사용 가능한 값

HF schema의 object-level fields:

```text
bbox
categories
diameter
length
decimal_stage
```

따라서 현재 mirror만으로 가능한 작업:

- fruit detection / crop extraction
- maturity / decimal-stage analysis
- diameter regression feasibility
- length regression feasibility
- image geometry ↔ measured dimension relation audit

### 3.2 HF mirror에서 직접 사용할 수 없는 값

HF mirror object schema에는 `weight`가 없다.

원 Zenodo `measurements.zip`에는 다음이 별도로 존재한다.

```text
data_size_freshWeight_condition_2022_*.csv
data_taggedFruit_diameter_2022.csv
data_taggedFruit_diameter_2023.csv
data_taggedFruit_length_2022.csv
data_taggedFruit_length_2023.csv
data_taggedFruit_freshMatter_2023.csv
```

따라서 다음을 검증하기 전에는 `KGCV image → fresh weight GT`가 있다고 간주하지 않는다.

```text
measurement file schema audit
→ tag / fruit identity key audit
→ image annotation identity와 measurement identity join 가능성 확인
→ 1:1 / 1:N / time-series relation 확인
→ leakage boundary 결정
```

**현재 판정: `WEIGHT_JOIN_AUDIT_REQUIRED`.**

### 3.3 Condition labels

원본 measurement는 fruit condition 5종을 제공한다.

```text
1 Normal
2 Wizened
3 Malformed
4 Wizened & Malformed
5 Overripe
```

이 값은 `SP/HI/MD/JM` 직접 label이 아니다.

가능한 역할:

- `Malformed` → quality override auxiliary target
- `Overripe` → ripeness/quality auxiliary target
- `Wizened` → sellability/quality auxiliary research

원본 condition은 보존하고 `JM` mapping은 Nongtori Decision Policy에서만 수행한다.

## 4. 외부 Ripeness 후보

### DATA-RIP-001 — Strawberry-DS

- 247 high-resolution RGB images
- Festival cultivar
- labels: Green / White / Early-Turning / Turning / Late-Turning / Red
- CC BY 4.0
- 역할: in-field ripeness auxiliary / detection
- 상태: `REVIEW_REQUIRED`

주의:
- cultivar/domain gap 존재
- 최종 M0~M4 mapping은 source definition + field calibration을 함께 본다.

### DATA-RIP-004 — Strawberry/Avocado longitudinal ripening dataset

- DOI: `10.17632/zysvgmxcyz.1`
- 1,333 original images; 14,630 figure includes augmentation
- strawberry + avocado
- strawberry stages: unripe / partially ripe / ripe / rotten
- longitudinal/day-by-day acquisition
- CC BY 4.0
- 역할: `POSTHARVEST_RIPENING_AUXILIARY`
- 상태: `REVIEW_REQUIRED`

주의:
- augmented images는 split 전에 원본 identity와 분리하면 leakage 위험이 큼
- post-harvest/domain 차이가 있으므로 production maturity label에 직접 합치지 않음
- `rotten`은 M4와 동치가 아니며 별도 deterioration state로 취급

### PAPER-RIP-001 — Seolhyang greenhouse 5-stage ripeness study (2026)

- Agriculture 2026, 16(14), 1550
- Pyeongtaek commercial greenhouse
- Seolhyang
- approximately 3,000 images
- visual classes: green / early turning / turning / late turning / red
- data availability: author request
- 역할: `REFERENCE_ONLY` until data access/license is cleared

가치:
- 설향 field-domain reference
- surface red distribution / ordinal error design 참고
- current Nongtori M0/M1 boundary issue와 비교 가능한 research reference

### DATA-RIP-005 — Multi-class strawberry ripeness detection candidate (2026 publication)

- public Kaggle dataset linked by publication
- 566 images / 1,169 annotated strawberry objects
- two commercial greenhouses, Türkiye
- labels: unripe / semi-ripe / fully-ripe
- 역할: coarse-stage robustness auxiliary candidate
- 상태: `REVIEW_REQUIRED`

주의:
- license를 source page에서 별도 확인하기 전 training approval 금지
- 3-class label을 M0~M4에 강제 확장하지 않음

## 5. 외부 Weight / Quality 후보

### DATA-QUAL-001 — ICRA 2022 strawberry weight dataset

Source repo: `imanlab/strawberry-pp-w-r-dataset`

제공:
- RGB
- background-removed RGB
- raw/colorized depth
- point cloud
- weight label
- keypoints / bbox / ripeness annotations

License:
- `CC-BY-NC-SA`
- repository explicitly states non-commercial use

판정:

```text
status = NON_COMMERCIAL_ONLY
role = REFERENCE_BENCHMARK_ONLY
production_pretraining = PROHIBITED unless separate permission is obtained
```

농토리 상용화를 전제로 하면 이 데이터는 모델 구조/metric/reference 확인에는 쓸 수 있지만 상용 weight model의 production training set에는 넣지 않는다.

### DATA-QUAL-002 — UC Davis Dryad Strawberry Database

Source:
- DOI: `10.25338/B8V308`
- provider: Dryad / University of California, Davis

Dataset:
- 1,611 individual strawberries
- 15 varieties
- 3 California production regions
- each berry photographed from 22 controlled RGB views
- manual shape classification
- manually measured maximal width / height
- weight with calyx and weight without calyx
- 3D scan / point cloud also available

License / commercial use:
- Dryad terms state submitted datasets are made public under a CC0 instrument and encourage unrestricted reuse.
- the dataset page shows no alternate restrictive license.
- current Nongtori registry status: `REVIEW_REQUIRED`, commercial-use candidate.

Why this is the strongest current weight candidate:

```text
fruit-level physical weight GT
+ many RGB views of the same fruit
+ dimensions / shape / 3D data
+ commercial reuse not blocked by NC clause
```

Approximate view count from the published acquisition protocol:

```text
1,611 fruits × 22 RGB views = 35,442 fruit views
```

Critical leakage rule:

```text
all 22 views of one strawberry MUST stay in the same split
split_group = FRUIT_ID
```

Before `APPROVED`:

1. download/audit `datasheet.xlsx`
2. confirm exact column names and units
3. prove picture filename ↔ fruit ID join
4. choose weight-with-calyx vs weight-without-calyx target consistent with Nongtori `Weight_g`
5. audit missing/duplicate IDs
6. create fruit-level immutable manifest

Domain limitation:
- controlled turntable/lighting
- post-harvest individual fruit
- multiple cultivars, not Seolhyang-specific greenhouse field imagery

Therefore:

```text
role = COMMERCIAL_WEIGHT_PRETRAINING_CANDIDATE
field_acceptance = NOT_ALLOWED
```

Use first for:
- geometry-only weight baseline
- RGB single-view / multi-view weight regression
- shape/weight representation pretraining

Then calibrate/fine-tune with Nongtori Seolhyang field data after field data readiness.

### PAPER-QUAL-001 — MMF-Net strawberry weight estimation (2025)

- Scientific Reports 2025
- 1,521 RGB-D pairs, 1,872 strawberry instances reported
- manual weight / length / diameter
- RGB + depth + point cloud + segmentation
- dataset/code: corresponding author on request
- article license: CC BY-NC-ND 4.0
- dataset reuse license는 별도 확인 필요

판정:

```text
status = REQUEST_ONLY / LICENSE_REVIEW_REQUIRED
role = ARCHITECTURE_REFERENCE
```

## 6. Commercial-use weight source ranking

현재 확인된 후보 우선순위:

| Priority | Source | Commercial training | Fruit-level weight | RGB linked | Domain note |
|---|---|---|---|---|---|
| 1 | DATA-QUAL-002 Dryad UC Davis | YES / CC0 candidate | YES | YES, 22 views/fruit | controlled postharvest |
| 2 | DATA-RIP-002 KGCV original | YES / CC BY 4.0 | YES in measurements | JOIN AUDIT REQUIRED | greenhouse, stronger domain match |
| Reference | DATA-QUAL-001 ICRA 2022 | NO | YES | YES | NC license |
| Reference | PAPER-QUAL-001 MMF-Net | UNCONFIRMED | YES | YES / RGB-D | author request |

Recommended combination after W0 audit:

```text
Dryad DATA-QUAL-002
  → clean commercial RGB weight pretraining / geometry baseline

KGCV DATA-RIP-002
  → greenhouse size/phenology + weight join if identity audit passes

NONGTORI_FIELD
  → final Seolhyang calibration / field acceptance
```

## 7. Weight Estimation V1 실험 게이트

현 시점에 바로 `SP/HI/MD/JM classifier`를 학습하지 않는다.

### Gate W0 — source audit

필수:
- image ↔ GT weight join key 증명
- g 단위 명확화
- fruit-level identity 확인
- 같은 fruit의 반복 촬영/time-series 여부 확인
- split leakage boundary 확정

### Gate W1 — simple regression baseline

W0 통과 후 비교:

```text
A. geometry-only: diameter / length → weight
B. RGB crop only → weight
C. RGB + predicted geometry → weight
D. multi-view aggregation if source provides multiple views per fruit
E. depth/3D only when commercial-use source allows it
```

Primary metrics:
- MAE(g)
- RMSE(g)
- grade-boundary error around 12g / 16g / 22g
- final weight-grade confusion

`R²`는 보조 metric이며 grade boundary error를 대체하지 않는다.

### Gate W2 — Nongtori grade policy simulation

```text
predicted weight
→ 22 / 16 / 12g thresholds
→ weight_grade
→ quality override
→ final_grade
```

평가 시 weight regression 오차가 실제 Grade 경계를 얼마나 넘나드는지 별도로 측정한다.

## 8. Ripeness V2 외부데이터 전략

현재 KGCV-RIPENESS-V001 benchmark를 변경하지 않는다.

새 외부데이터는 `v001`에 덧붙이지 않고 successor source audit를 거쳐 `v002+ snapshot`으로 만든다.

순서:

```text
source audit
→ original identity / augmentation provenance
→ label mapping confidence
→ duplicate / cross-source leakage audit
→ source-aware split
→ clean baseline
→ KGCV-only baseline과 비교
```

필수 비교:

- KGCV-only
- KGCV + DATA-RIP-001
- approved sources only combined
- per-source validation

전체 validation 평균만 좋아지고 특정 source에서 붕괴하는 경우 승인하지 않는다.

## 9. Stop condition

현재 외부 데이터만으로 다음을 주장하지 않는다.

- 설향 field weight accuracy
- production SP/HI/MD/JM accuracy
- M0~M4 field accuracy
- KGCV image와 fresh weight가 자동 1:1 join된다는 주장
- Dryad controlled-view 성능을 스마트팜 field 성능으로 간주

현장 데이터 정리 전까지 완료 목표:

```text
external source audit complete
+ commercial-use weight source identified
+ fruit-ID-safe split policy frozen
+ KGCV dimension/weight join audit tooling ready
+ Ripeness V2 / Weight V1 experiment gates frozen
```
