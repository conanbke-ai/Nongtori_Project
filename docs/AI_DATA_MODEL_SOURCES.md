# Nongtori AI / Data / Model Source Registry

외부 데이터셋, 논문, 공개 모델/공식 구현의 출처와 의사결정 이력을 영구 추적한다.

## 1. 원칙

1. 사용 전 Source ID를 부여한다.
2. 원본 출처와 다운로드 mirror를 분리한다.
3. 원본 label은 보존하고 Nongtori mapping을 별도 관리한다.
4. 논문 reported metric과 Nongtori reproduced/test/field metric을 섞지 않는다.
5. 저자 공식 코드와 제3자 재구현을 구분한다.
6. license, commercial use, redistribution 조건을 기록한다.
7. 실제 농장 원본은 `NONGTORI_FIELD`로 분리한다.
8. 학습에는 dataset version/split, model source, experiment, Optuna provenance를 남긴다.
9. `REJECTED / RETIRED / SUPERSEDED` source도 삭제하지 않는다.
10. 상용화 가능성이 있는 Nongtori production model에는 `NON_COMMERCIAL_ONLY` source를 혼입하지 않는다.

## 2. Lifecycle

```text
DISCOVERED
→ REVIEW_REQUIRED
→ DOWNLOADED
→ AUDITED
→ APPROVED
→ NORMALIZED
→ SNAPSHOT_READY
→ IN_USE
```

분기 상태:

- `REJECTED`
- `RETIRED`
- `SUPERSEDED`
- `AUTH_REQUIRED`
- `NON_COMMERCIAL_ONLY`

`DOWNLOADED`는 학습 승인 상태가 아니다.

## 3. Source ID

- `DATA-RIP-###`
- `DATA-QUAL-###`
- `DATA-DIS-###`
- `DATA-PEST-###`
- `DATA-FIELD-###`
- `DATA-MKT-###`
- `PAPER-RIP-###`
- `PAPER-QUAL-###`
- `PAPER-DIS-###`
- `PAPER-YIELD-###`
- `PAPER-PRICE-###`
- `MODEL-RIP-###`
- `MODEL-QUAL-###`
- `MODEL-DIS-###`
- `MODEL-TRACK-###`
- `MODEL-PRICE-###`

## 4. 현재 Registry

| Source ID | Provider / Source | 목적 | License / access | 상태 |
|---|---|---|---|---|
| DATA-RIP-001 | Mendeley Data / Strawberry-DS v1 | 숙도/객체탐지 reference | CC BY 4.0 확인, public download | REVIEW_REQUIRED |
| DATA-RIP-002 | Project-AgML / HF `strawberry_growth_detection` + Zenodo original | detection/ripeness/size, weight join 후보 | CC BY 4.0 | AUDIT IN PROGRESS |
| DATA-RIP-003 | AI-Hub 지능형 수직농장 통합 데이터(딸기), key 596 | 설향/금실/환경 reference | 승인 + API key + `aihubshell` 필요 | AUTH_REQUIRED |
| DATA-RIP-004 | Mendeley longitudinal strawberry/avocado ripening | 수확후 ripening auxiliary | CC BY 4.0 | REVIEW_REQUIRED |
| DATA-QUAL-001 | ICRA 2022 strawberry picking/weight dataset | RGB/RGB-D weight architecture/reference | CC-BY-NC-SA, commercial 금지 | NON_COMMERCIAL_ONLY |
| DATA-QUAL-002 | UC Davis Dryad Strawberry Database | RGB weight/geometry pretraining 후보 | Dryad CC0, commercial use allowed | REVIEW_REQUIRED |
| DATA-DIS-001 | Strawberry disease multimodal public dataset 후보 | 질병 보조 | 비상업 조건 재확인 | REVIEW_REQUIRED |
| DATA-PEST-001 | Roboflow / Strawberry Dataset | 딸기 field-context 병해충 탐지 후보 | CC BY 4.0 / API key acquisition | REVIEW_REQUIRED |
| DATA-PEST-002 | Gent Lab / TSSM Detection v2 + miteVision | 응애 morphology/life-stage reference | CC BY 4.0 / API key acquisition | REVIEW_REQUIRED |
| DATA-FIELD-001 | NONGTORI_FIELD | 실제 현장 사진/영상 | PRIVATE | IN_USE |
| MODEL-TRACK-001 | ByteTrack | MOT baseline | 공식 repo/license audit | REVIEW_REQUIRED |
| MODEL-TRACK-002 | BoT-SORT | moving-camera MOT candidate | 공식 repo/license audit | REVIEW_REQUIRED |
| MODEL-RIP-001 | DigitalAgUMN / KGCV_Strawberry official implementation | 숙도/phenology source-method reference | license review required | REVIEW_REQUIRED |
| MODEL-PEST-001 | mswiseman / miteVision official implementation | TSSM source-method reference | license review required | REVIEW_REQUIRED |
| POLICY-GRADE-001 | NAQS / Korean agricultural standard | 딸기 품질등급·크기구분 reference | official standard | REVIEW_REQUIRED |
| POLICY-GRADE-002 | Hadong strawberry Nonghyup direct-sales grading rule | field/business 12/16/22g grading policy | user-confirmed field source | IN_USE |

실제 기계 판독 가능한 source record는 `ml/data_pipeline/sources/*.json`을 canonical input으로 사용한다. 문서 표와 JSON이 충돌하면 최신 검증 근거를 반영해 둘을 같은 변경에서 정합화한다.

### DATA-RIP-001

- DOI: `10.17632/z6dtfdpzz8.1`
- version: `1`
- 247 RGB 이미지 + YOLO annotation
- 원본 maturity labels: Green, White, Early-Turning, Turning, Late-Turning, Red
- CC BY 4.0
- Nongtori 0~4 mapping은 audit 후 별도 mapping version으로 결정

### DATA-RIP-002

- 원 연구 데이터 DOI: `10.5281/zenodo.10957909`
- HF mirror: `Project-AgML/strawberry_growth_detection`
- 현재 registry pin: `70f6277a609fb80fa18b431dccd04b9f09c876e0`
- 1,477 rows / 3,997 boxes / 7 categories
- HF object metadata: `diameter`, `length`, `decimal_stage`
- 원 Zenodo `measurements.zip`: fruit-level fresh weight/fresh matter + condition + tagged fruit dimension tables
- License: CC BY 4.0
- image/tagged fruit와 fresh-weight table의 identity join은 `WEIGHT_JOIN_AUDIT_REQUIRED`

### DATA-RIP-003

- AI-Hub dataset key: `596`
- registry version: `1.2`
- official `aihubshell` 사용
- 다운로드 승인과 `AIHUB_API_KEY` 없이는 `AUTH_REQUIRED`
- 인증 실패를 다른 공개 dataset으로 자동 대체하지 않는다.

### DATA-RIP-004

- DOI: `10.17632/zysvgmxcyz.1`
- original images + longitudinal ripening progression
- strawberry labels: unripe / partially ripe / ripe / rotten
- CC BY 4.0
- post-harvest/domain 차이 때문에 `POSTHARVEST_RIPENING_AUXILIARY`로만 사용
- augmentation identity를 원본과 섞어 split하지 않는다.

### DATA-QUAL-001

- official repo: `imanlab/strawberry-pp-w-r-dataset`
- RGB / background-removed RGB / depth / point cloud / weight label
- license: `CC-BY-NC-SA`
- repository가 free non-commercial use를 명시
- production/commercial training에는 사용 금지
- architecture/metric/reference benchmark 용도만 허용

### DATA-QUAL-002

- DOI: `10.25338/B8V308`
- provider: Dryad / UC Davis
- 1,611 individual strawberries
- 15 varieties / 3 California production regions
- 각 fruit에 controlled RGB 22 views
- manual shape classification, width/height measurement
- weight with calyx + weight without calyx measured on OHAUS Scout Pro SP602
- Dryad terms publish datasets under CC0; dataset page에서 별도 제한이 표시되지 않음
- 역할: `COMMERCIAL_WEIGHT_PRETRAINING_CANDIDATE`

필수 audit:

```text
datasheet column/unit 확인
→ image filename ↔ fruit ID join 증명
→ Nongtori Weight_g와 일치하는 weight target 선택
→ 22 views를 fruit ID group으로 묶어 split leakage 차단
```

주의:
- controlled turntable / post-harvest domain이라 실제 스마트팜 camera domain과 다름
- production field acceptance가 아니라 RGB weight pretraining + geometry baseline에 우선 사용

## 5. 가격 데이터 Source 범주

공식/준공식 시장 데이터는 다음 source family로 관리한다.

- 농림축산식품 관련 공공 API
- 도매시장/법인 거래 정보
- 품목/품종/등급/포장/단위 코드

각 endpoint는 `DATA-MKT-###` source record를 만들고 unit normalization과 cutoff 사용 가능성을 audit한다.

## 6. Source Record

```yaml
source_id: DATA-QUAL-002
source_type: dataset
provider: dryad
title: A Strawberry Database: Geometric Properties, Images and 3D Scans
original_url: https://doi.org/10.25338/B8V308
version_or_revision: "2018-02-08"
license: CC0-1.0
license_checked_at: 2026-09-17
redistribution_allowed: allowed
commercial_use: allowed
status: REVIEW_REQUIRED
retrieval: {}
original_labels: []
nongtori_mapping: {}
notes: ...
```

논문/모델은 `official_code_url`, `official_code_commit`, `pretrained_weights_url`, `reported_metrics`, `reproduced_metrics`, `reference_level`을 추가한다.

## 7. Experiment provenance

```yaml
experiment_id: EXP-WGT-001
dataset_source_ids: []
dataset_manifest_hash: ...
train_split: ...
validation_split: ...
test_split: ...
field_test_source_ids: []
model_source_ids: []
paper_reference_ids: []
optuna_study: ...
optuna_best_trial: ...
optuna_best_params: {}
final_checkpoint_hash: ...
```

## 8. Git 정책

Git에 저장:
- registry/source record
- manifest/checksum/label mapping/split manifest
- downloader/audit/normalization script
- model config/reference/metrics
- Optuna summary

Git에 저장하지 않음:
- 대용량 raw 공개 데이터
- 재배포 제한 데이터
- 실제 농장 private 원본
- 대용량 checkpoint/weights


### DATA-PEST-001

- Role: `STRAWBERRY_FIELD_CONTEXT_PEST_DETECTION_CANDIDATE`
- Target label: `Tetranychus Urticae`
- Usefulness: strawberry-context pest imagery.
- Gate before training: exact downloadable version, class counts, split integrity, duplicate/augmentation provenance.
- This source alone is not accepted as field validation.

### DATA-PEST-002

- Role: `TSSM_MORPHOLOGY_AND_LIFE_STAGE_REFERENCE`
- Official project reference: Gent Lab / miteVision.
- Multiple mite/life-stage and non-target arthropod labels are preserved at source level.
- Nongtori may later define an explicit TSSM-positive label-collapse policy, but must not silently collapse labels before an audit snapshot.
- Host/domain mismatch remains material; this source is not a substitute for strawberry-field acceptance.



## Source-alignment governance

Model/data source registration is not sufficient by itself. Before a new model family is promoted, Nongtori must record:

- official source architecture;
- target definition;
- preprocessing;
- training recipe;
- evaluation protocol;
- every Nongtori deviation and its rationale.

Current corrective classifications:

- `MODEL-PEST-001`: source-method reference is YOLO11-Large v210; Faster R-CNN V001/V002 are historical Nongtori baselines, not source reproductions.
- `MODEL-RIP-001`: source-method references are KGCV Faster R-CNN stage detection and DenseNet121 trait/decimal-stage estimation; current EfficientNet-B0 is a Nongtori development benchmark.
- `POLICY-GRADE-001`: official strawberry quality grade and size class are distinct.
- `POLICY-GRADE-002`: Nongtori 12/16/22g is the user-confirmed Hadong strawberry Nonghyup direct-sales field/business grading rule. It remains valid for that operating context and must stay distinct from the national official size and quality standards.

Canonical audit: `docs/SOURCE_ALIGNMENT_AUDIT_V1_20261015.md`.

---

## 2026-11-27 응애 우선 원천 데이터 수집

**Status: DISCOVERY / NOT DOWNLOADED / NOT TRAINING_READY.** 기타 병해충의 광범위한 검색·다운로드는 일단 후순위로 두고, 점박이응애 `Tetranychus urticae` 관련 **열화상·환경·현장 확진 자료**를 최우선 확보한다. RGB 객체 탐지 데이터는 보조 evidence 전용이다. 기존 등록된 공개 데이터 소스와 해시가 중복되는 파일을 수집하지 않는다.

### 우선 자료군 및 접근 판단

| 우선 | 출처 | 내용 | 상태 / 경계 |
|---|---|---|---|
| P0 | 기존 Nongtori 현장 촬영 FLIR/열화상·환경 기록 | 잎/참조 온도, 촬영 시각·구역·감염 확인 기록 연결 | 실제 원본 파일/온도 행렬 내보내기 및 label join 미확인; SOURCE ACCESS REQUIRED |
| P0 | Dryad `10.5061/dryad.4j0zpc8jd` | 응애·알 밀도, 잎 온도, 수분/영양 등 실측 | 공개 연구 데이터; **옥수수**, 딸기 학습/현장 검증 대체 금지; 파일·컬럼·단위 감사 필요 |
| P0 | Smart Agricultural Technology `10.1016/j.atech.2026.101939` | 딸기/오이 응애 초분광 무증상·초기 감염, XGBoost 연구, 1,120 연구 스냅샷 언급 | 논문 공개, 학습 원시 스펙트럼·라벨 파일의 제공/재사용 권한은 UNVERIFIED; 열화상과 센서가 다름 |
| P1 | Smart Agricultural Technology `10.1016/j.atech.2025.101193` | 딸기 `T. urticae` 시간별 초분광 관측 | 기존 관련 연구 인용과 중복 등록 여부부터 조사; 원본 공개 여부 미확인 |
| P1 | `10.1016/j.atech.2023.100229` | 딸기/응애/포식성 응애 스마트폰 이미지 3,013장 연구 | 논문 명시: 원천 데이터 confidential; DOWNLOADABLE로 취급 금지; 공개 연구 방법만 참조 |
| P1 | Gent Lab `miteVision`, `DATA-PEST-002` | 기존 morphology/life stage RGB reference; 약 1,500+ image / ~32k objects full research family | **이미 등록 및 스냅샷 있음**. 원천 버전/스냅샷 v210과 v209/v211·Zenodo test 세트 간 중복 해시 확인 전 다운로드 금지 |
| P2 | 기타 병해충 외부 후보 | 진딧물·총채벌레·병해 | 응애 핵심 P0 수집·감사 착수 이후에만 제한적으로 확보 |

### 실제 확보 목표 및 검증 기준

- `DISCOVERED`, `ACCESSIBLE`, `DOWNLOADED`, `HASH_VERIFIED`, `ANNOTATED`, `TRAINING_READY`를 별도 집계. 논문에 언급된 사진 수를 실제 확보 수로 표현하지 않는다.
- 열화상/잎 온도는 radiometric 온도값인지, 장비 앱에서 선택한 지점의 일부 측정값인지 구분. 파일 형식, 단위, 시각, 대상 잎/기준 잎 ROI 및 현장 감염 확진 근거를 연결할 수 없으면 위험 모델의 양성·음성 학습에 사용하지 않는다.
- 가능하면 같은 잎/구역에서 감염 확인 전후의 반복 관측, 확인된 정상 대조군, 수분 스트레스/광량 등 교란 조건을 수집. 응애 밀도·측정 시각을 보존하고, `Health`/`Risk_Status` 또는 RGB 미탐을 자동 응애 음성으로 변환 금지.
- 프레임·동일 잎·동일 개체·동일 세션을 독립 표본으로 과다 계산하지 않으며 split 원자성·원본 보존·허가/라이선스·immutable snapshot 정책 유지.
- P0 원본 접근 불가 시 추가 파운데이션 모델·샤딩·대규모 파인튜닝으로 문제를 덮지 않는다. 작은 검증 배치에서 실제 원본 파일과 라벨 대응을 증명하는 게 우선이다.
- 2026-11-27 현재 이 문서는 **공개 근거 조사 및 우선순위 결정만** 기록한다. 다운로드한 신규 원천 바이트, 현장 파일 목록, SHA-256, 학습 성능은 확인하지 않았다.
