# Nongtori AI / Data / Model Source Registry

이 문서는 농토리에서 사용하는 외부 데이터셋, 논문·학술자료, 공개 모델·공식 구현의 출처와 실제 활용 방식을 추적하기 위한 canonical registry다.

## 원칙

1. 외부 데이터·논문·모델을 농토리에 도입하기 전에 반드시 이 문서 또는 하위 source record에 출처를 등록한다.
2. 원본 출처와 실제 다운로드 경로(mirror)는 분리해서 기록한다.
3. 원본 라벨은 변경하지 않는다. 농토리 라벨은 별도 mapping으로 관리한다.
4. 논문 수치(reported metric)와 농토리에서 재현한 수치(reproduced metric)는 절대 섞지 않는다.
5. 논문 저자의 공식 코드와 제3자 재구현 코드를 구분한다.
6. 라이선스·비상업 조건·재배포 제한을 기록하고, 제한이 있는 원본 데이터/가중치는 GitHub에 커밋하지 않는다.
7. 실제 농장 데이터는 `NONGTORI_FIELD`로 구분하고 외부 공개 데이터와 혼합 출처로 저장하지 않는다.
8. 모델 학습에는 데이터셋 버전, split, 모델 base/reference, Optuna study/params를 함께 기록한다.

## Source ID 규칙

- `DATA-RIP-###`: 숙도/과실 데이터
- `DATA-DIS-###`: 질병 데이터
- `DATA-PEST-###`: 해충 데이터
- `DATA-FIELD-###`: 농토리 자체 현장 데이터
- `DATA-MKT-###`: 시장/가격 데이터
- `PAPER-RIP-###`: 숙도/과실 논문
- `PAPER-DIS-###`: 질병/해충 논문
- `PAPER-YIELD-###`: 생육/수확 관련 논문
- `PAPER-PRICE-###`: 가격 예측 논문
- `MODEL-RIP-###`, `MODEL-DIS-###`, `MODEL-PRICE-###`: 공개 모델/공식 구현

## 데이터셋 Registry

| Source ID | Platform / Provider | Dataset | Original source | License | Original labels / target | Nongtori use | Status |
|---|---|---|---|---|---|---|---|
| DATA-RIP-001 | Mendeley Data / Strawberry-DS authors | Strawberry-DS | DOI `10.17632/z6dtfdpzz8.1` | CC BY 4.0 | Green, White, Early-Turning, Turning, Late-Turning, Red | 숙도 모델 학습·검증 reference | CANDIDATE_PRIMARY |
| DATA-RIP-002 | Project-AgML / Hugging Face mirror | strawberry_growth_detection | 원 연구/데이터 출처는 source record에서 별도 고정 | CC BY 계열 — 재확인 후 고정 | flower, green, white, turning red, red, overripe 등 | 과실 detection, 숙도/overripe, 크기·생육 reference | CANDIDATE_PRIMARY |
| DATA-DIS-001 | Qin2006 / Hugging Face | Strawberry-MM-Straw5 | source record에서 원 논문/저자 링크 고정 | CC BY-NC-SA 4.0 | normal, gray mold, powdery mildew, black spot, overripe | 잿빛곰팡이·흰가루·과숙 보조 | NON_COMMERCIAL_ONLY |
| DATA-PEST-001 | Ethan0300 / Hugging Face | Strawberry_12 | source record에서 원 출처 확인 후 고정 | MIT 표기 — 원 출처 audit 필요 | 12 classes; 다운로드 후 `data.yaml` audit | 병해충 지원 후보 판정 | LABEL_AUDIT_REQUIRED |
| DATA-RIP-003 | AI-Hub | 지능형 수직농장 통합 데이터(딸기), dataset 596 | AI-Hub dataset 596 | AI-Hub 이용조건 | 설향/금실 생육·환경·수확 관련 | 설향 domain, 환경/수확 기록 reference | MANUAL_AUTH_REQUIRED |
| DATA-FIELD-001 | NONGTORI_FIELD | 농토리 자체 응애 현장 데이터 | Private field source | PRIVATE | spider mite field observations | 최종 FIELD_TEST / 향후 fine-tuning 후보 | PRIVATE_FIELD |

> 위 표의 `CANDIDATE_*` 항목은 실제 자동 다운로드·파일/라벨/라이선스 audit가 끝나기 전까지 학습 승인 완료로 간주하지 않는다.

## 논문 / 학술자료 Registry

| Source ID | Paper / Study | Year | DOI / Official page | Task | Nongtori use | Reference level |
|---|---|---:|---|---|---|---|
| PAPER-RIP-001 | Strawberry-DS 관련 6단계 숙도 detection 연구 | 2023 | source record에서 DOI/논문 링크 고정 | Green→Red 6단계 숙도 detection | 외부 원본 라벨 체계와 0~4 normalization 검토 | PRIMARY_REFERENCE_CANDIDATE |
| PAPER-YIELD-001 | KGCV-Strawberry | 2024 | source record에서 논문 DOI 및 저자 공식 저장소 고정 | fruit detection, decimal phenological stage, growth/yield | 숙도 연속점수/과실 분석 구조 참조 | PRIMARY_REFERENCE_CANDIDATE |
| PAPER-YIELD-002 | PheMuT | 2026 | source record에서 DOI 및 저자 공식 저장소 고정 | visual+weather multi-modal yield forecasting | v1 범위 밖, 향후 고급 reference | FUTURE_REFERENCE |

## 공개 모델 / 코드 Registry

| Source ID | Base / Repository | Owner | Official? | License | Task | Nongtori use | Status |
|---|---|---|---|---|---|---|---|
| MODEL-RIP-001 | KGCV-Strawberry official implementation | 논문 저자 연구팀 | YES | repository license 확인 후 고정 | detection + decimal stage | 숙도/과실 reference reproduction | REVIEW_REQUIRED |
| MODEL-RIP-002 | Ultralytics YOLO baseline | Ultralytics | Official framework | repository/model license 별도 확인 | detection/classification | 동일 split baseline | BASELINE_CANDIDATE |

## Source Record 필수 항목

각 실제 source record는 최소 다음 필드를 포함한다.

```yaml
source_id: DATA-RIP-001
source_type: dataset
platform: Mendeley Data
provider: "..."
title: Strawberry-DS
original_url: "..."
doi: "10.17632/z6dtfdpzz8.1"
retrieval_url: "..."       # mirror가 있으면 별도 기록
retrieval_method: "..."    # HF snapshot / Kaggle API / AI-Hub API 등
version_or_revision: "..."
license: CC-BY-4.0
license_checked_at: YYYY-MM-DD
original_labels: []
nongtori_usage: "..."
nongtori_mapping: "..."
redistribution_allowed: true|false|unknown
commercial_use: allowed|non_commercial|review_required
status: candidate|approved|rejected|auth_required
notes: "..."
```

논문/모델은 아래 항목도 추가한다.

```yaml
paper_title: "..."
authors: []
year: 2024
journal: "..."
official_code_url: "..."
official_code_commit: "..."
pretrained_weights_url: "..."
reported_metrics: {}
reproduced_metrics: {}
reference_level: primary|official_code|third_party|paper_only
```

## 학습 실험 연결 규칙

모든 실험 결과에는 다음 provenance를 남긴다.

```yaml
experiment_id: EXP-RIP-001
dataset_source_ids:
  - DATA-RIP-001
  - DATA-RIP-002
dataset_manifest_hash: "..."
train_split: "..."
validation_split: "..."
test_split: "..."
field_test_source_ids: []
model_source_ids:
  - MODEL-RIP-002
paper_reference_ids:
  - PAPER-RIP-001
optuna_study: "..."
optuna_best_trial: 0
optuna_best_params: {}
final_checkpoint_hash: "..."
```

## 저장소 / 원본 파일 정책

GitHub에 저장:

- 이 registry 및 개별 source record
- dataset manifest / checksum / label mapping
- 다운로드·audit·normalization 스크립트
- 모델 config / source reference / metrics
- Optuna best params 및 trial summary

GitHub에 저장하지 않음:

- 공개 데이터셋의 대용량 raw 이미지 원본
- 라이선스상 재배포가 제한된 데이터
- 농토리 실제 농장 private 원본
- 대용량 학습 checkpoint/weights (별도 artifact 저장 정책을 따름)

## 변경 규칙

새 데이터셋·논문·모델을 참조하는 코드 또는 학습 config를 추가할 때 source registry 등록을 같은 변경 범위에서 수행한다. 출처를 확인할 수 없는 자료는 모델 학습의 canonical source로 승격하지 않는다.
