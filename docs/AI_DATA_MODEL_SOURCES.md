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
- `DATA-DIS-###`
- `DATA-PEST-###`
- `DATA-FIELD-###`
- `DATA-MKT-###`
- `PAPER-RIP-###`
- `PAPER-DIS-###`
- `PAPER-YIELD-###`
- `PAPER-PRICE-###`
- `MODEL-RIP-###`
- `MODEL-DIS-###`
- `MODEL-TRACK-###`
- `MODEL-PRICE-###`

## 4. 현재 Registry

| Source ID | Provider / Source | 목적 | License / access | 상태 |
|---|---|---|---|---|
| DATA-RIP-001 | Mendeley Data / Strawberry-DS v1 | 숙도/객체탐지 reference | CC BY 4.0 확인, public API 다운로드 가능 | REVIEW_REQUIRED |
| DATA-RIP-002 | Project-AgML / Hugging Face `strawberry_growth_detection` | detection/ripeness/size reference | CC BY 4.0 확인, 약 6.75GB, revision pin | REVIEW_REQUIRED |
| DATA-RIP-003 | AI-Hub 지능형 수직농장 통합 데이터(딸기), dataset key 596 | 설향/금실/환경 reference | 승인 + API key + `aihubshell` 필요 | AUTH_REQUIRED |
| DATA-DIS-001 | Strawberry disease multimodal public dataset 후보 | 질병 보조 | 비상업 조건 재확인 | REVIEW_REQUIRED |
| DATA-PEST-001 | Strawberry pest public dataset 후보 | 병해충 label audit | 원 출처/label/license audit 필요 | REVIEW_REQUIRED |
| DATA-FIELD-001 | NONGTORI_FIELD | 실제 현장 사진/영상 | PRIVATE | IN_USE |
| MODEL-TRACK-001 | ByteTrack | MOT baseline | 공식 repo/license audit | REVIEW_REQUIRED |
| MODEL-TRACK-002 | BoT-SORT | moving-camera MOT candidate | 공식 repo/license audit | REVIEW_REQUIRED |

실제 기계 판독 가능한 source record는 `ml/data_pipeline/sources/*.json`을 canonical input으로 사용한다. 문서 표와 JSON이 충돌하면 최신 검증 근거를 반영해 둘을 같은 변경에서 정합화한다.

### DATA-RIP-001

- DOI: `10.17632/z6dtfdpzz8.1`
- version: `1`
- 247 RGB 이미지 + YOLO annotation
- 원본 maturity labels: Green, White, Early-Turning, Turning, Late-Turning, Red
- Mendeley public API로 version 고정 다운로드
- Nongtori 0~4 mapping은 **아직 확정하지 않음**. audit 후 별도 mapping version으로 결정

### DATA-RIP-002

- 원 연구 데이터 DOI: `10.5281/zenodo.10957909`
- HF mirror: `Project-AgML/strawberry_growth_detection`
- 현재 registry pin: `70f6277a609fb80fa18b431dccd04b9f09c876e0`
- 1,477 rows / 3,997 boxes / 7 categories
- mirror 전체 크기 약 6.75GB
- `huggingface_hub.snapshot_download` 사용

### DATA-RIP-003

- AI-Hub dataset key: `596`
- registry version: `1.2`
- official `aihubshell` 사용
- 다운로드 승인과 `AIHUB_API_KEY` 없이는 `AUTH_REQUIRED`
- 인증 실패를 다른 공개 dataset으로 자동 대체하지 않는다.

## 5. 가격 데이터 Source 범주

공식/준공식 시장 데이터는 다음 source family로 관리한다.

- 농림축산식품 관련 공공 API
- 도매시장/법인 거래 정보
- 품목/품종/등급/포장/단위 코드

각 endpoint는 `DATA-MKT-###` source record를 만들고 unit normalization과 cutoff 사용 가능성을 audit한다.

## 6. Source Record

```yaml
source_id: DATA-RIP-001
source_type: dataset
provider: mendeley
title: Strawberry-DS
original_url: ...
version_or_revision: "1"
license: CC-BY-4.0
license_checked_at: YYYY-MM-DD
redistribution_allowed: allowed_with_attribution
commercial_use: allowed_with_attribution
status: REVIEW_REQUIRED
retrieval: {}
original_labels: []
nongtori_mapping: {}
notes: ...
```

논문/모델은 `official_code_url`, `official_code_commit`, `pretrained_weights_url`, `reported_metrics`, `reproduced_metrics`, `reference_level`을 추가한다.

## 7. Experiment provenance

```yaml
experiment_id: EXP-RIP-001
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
