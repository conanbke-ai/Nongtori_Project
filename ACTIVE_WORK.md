# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- GitHub `delete_branch_on_merge=true`: merged feature branch 자동 삭제

## Canonical 상태

| Workstream | Canonical | 상태 | 다음 단계 |
|---|---|---|---|
| Design Freeze / ingestion / source relation | `main`, PR #1~#12 | MERGED / DESIGN_FROZEN | 정책 유지 |
| KGCV live metadata audit | `main`, PR #13 | MERGED | evidence 유지 |
| KGCV normalized manifest | `main`, PR #14 | MERGED | v001 mapping 유지 |
| KGCV asset SHA-256 + atomic split | `main`, PR #15 | MERGED | snapshot identity 유지 |
| KGCV Ripeness Training Snapshot v001 | `main`, PR #16 | FROZEN | immutable descriptor/checksum 유지 |
| Ripeness Baseline v001~v006 | `main` + historical experiment branches/PRs | EXECUTED / RECORDED | rejected directions 반복 금지 |
| Ripeness V007 + V008 benchmark | `main`, PR #23 | MERGED / BENCHMARK_FROZEN | downloaded-data benchmark evidence 유지 |
| Field data readiness v001 | `main`, PR #24 | MERGED | Drive/field 정리와 독립적으로 readiness gate 유지 |
| Ripeness V009 ordinal head | `feat/ripeness-v009-ordinal-head`, PR #25 | EXECUTED / REJECTED | 결과 문서화 후 merge → ConvNeXt-Tiny screening |

## Downloaded benchmark scope

Current model research may continue on the already downloaded and frozen `KGCV-RIPENESS-V001` snapshot even while Drive/field data is still being organized.

Rules:
- Drive/field data: excluded from current benchmark experiments;
- field inventory incompleteness does not block downloaded-data research;
- test split remains closed during screening/tuning;
- results are development-benchmark evidence only;
- no field/production claim;
- no silent reuse of field-label assumptions.

## KGCV-RIPENESS-V001 frozen facts

- Source: `DATA-RIP-002` / Project-AgML KGCV
- Physical images: 1,477 / 1,477 SHA-256 verified
- Unique SHA-256: 1,477
- Byte-identical duplicate groups: 0
- Object rows: 3,997
- Snapshot eligible: 3,162
- Excluded: flower 539, unresolved turning-red 296
- Maturity distribution: M0 1,571 / M1 731 / M4 860
- Split: train 2,243 / valid 486 / test 433
- Manifest SHA-256: `4a99618d7024a960f4f2431b17feaca2088415c2d14149be859df758f8985b9f`
- Eligible assignment SHA-256: `5e2424f7c26d84e4f8d43ca90ba60b46806eb9d7bb361669c8b42ad27f2040ea`
- Snapshot descriptor: `snapshots/KGCV_RIPENESS_V001.json`
- Snapshot documentation: `docs/TRAINING_SNAPSHOT_KGCV_V001.md`

`turning red`는 field calibration 전까지 v001에 편입하지 않는다. 이후 정책 변경은 v001 수정이 아니라 v002+ snapshot으로 생성한다.

## Ripeness benchmark current conclusion

### V007 paired confirmation

EfficientNet-B0 vs ResNet-18, paired seeds `20260911/12/13`:

| Metric | ResNet-18 | EfficientNet-B0 |
|---|---:|---:|
| Macro F1 mean | 0.9614 | **0.9686** |
| Accuracy mean | 0.9643 | **0.9698** |
| Ordinal MAE ↓ | 0.0418 | **0.0322** |
| Weighted Kappa | 0.9734 | **0.9771** |

EfficientNet-B0 won Macro F1 on 2/3 paired seeds and improved all aggregate primary/supporting metrics.

### V008 residual audit

Seed `20260912`, 486 validation samples:

- EfficientNet errors: 12
- ResNet errors: 18
- shared same error: 8
- EfficientNet M0→M1: 10
- EfficientNet M1→M0: 2
- M4 errors: 0

Interpretation: current residual error is highly localized at the M0/M1 boundary.

### V009 ordered cumulative ordinal head — REJECTED

Seed `20260910`, validation only:

| Metric | EfficientNet softmax | Ordinal head |
|---|---:|---:|
| Macro F1 | **0.9741** | 0.9464 |
| Accuracy | **0.9753** | 0.9527 |
| Ordinal MAE ↓ | **0.0309** | 0.0514 |
| Weighted Kappa | **0.9781** | 0.9670 |
| M1 F1 | **0.9502** | 0.8856 |

Ordinal-head failure pattern:
- M0→M1 reduced from 5 to 1;
- but M1→M0 increased from 6 to 21;
- M1 recall fell from `0.9459` to `0.8018`;
- broad primary/ordinal metrics all regressed.

Decision:
- reject current ordered cumulative threshold formulation;
- no paired multi-seed confirmation;
- no threshold/BCE-weight micro-sweep;
- do not generalize this rejection to all ordinal methods.

Canonical result: `docs/experiments/ripeness/EXP-RIP-009_ORDINAL_HEAD_RESULT.md`

## Current model status

```text
Snapshot      : KGCV-RIPENESS-V001
Role          : development benchmark
Preferred net : EfficientNet-B0 softmax
Test tuning   : prohibited
Field status  : NOT FIELD VALIDATED
Production    : NOT APPROVED
```

## Next downloaded-data experiment

Candidate: **ConvNeXt-Tiny backbone screening** under the same frozen snapshot and validation-only policy.

Reason:
- V007 showed architecture representation is a productive axis;
- V006 and V009 both failed to improve with ordinalization strategies;
- V009 head-only structural change strongly regressed M1;
- ConvNeXt-Tiny is a distinct modern convolutional backbone already retained in the backlog;
- resource cost must be evaluated with validation score.

Controlled plan:
1. EfficientNet-B0 softmax baseline under the current recipe.
2. ConvNeXt-Tiny, ImageNet pretrained.
3. Same frozen snapshot, train/valid split, 224 input, augmentation, weighted CE, AdamW, LR `5e-5`, batch 32, validation Macro F1 selection.
4. Record parameter count, VRAM, epoch runtime, Macro F1, M1 F1, Ordinal MAE, Kappa, confusion.
5. Clear regression → reject; small/positive signal → paired 3-seed confirmation.
6. Test split remains closed.

## Field data / label status

Canonical Google Sheet: `딸기_프로젝트`

Field/Drive data remains a separate workstream and is not required for the current downloaded-data benchmark. `FIELD_DATA_READINESS_POLICY.md` remains canonical for later field snapshot promotion.

## Logging / Observability

- `docs/LOGGING_OBSERVABILITY_STANDARD.md` canonical 적용
- console / run.log: human-readable progress/metric/checkpoint/error 중심
- `events.jsonl`: structured machine-readable detail
- run summary / metrics / checkpoint hash / retry / stack trace 기본 기록
- regression은 R²/MAE/RMSE, classification/ordinal은 task-specific metric을 기본 기록

## 데이터 안전

- Google Sheets/외부 원본/현장 사진·영상은 read-only source
- raw image는 Git에 commit하지 않음
- immutable snapshot은 descriptor + manifest checksum + asset hash + frozen split으로 재현
- test set tuning 금지
- 기존 snapshot은 수정하지 않고 새 version 생성

## Branch hygiene

- feature branch는 실제 독립 workstream에만 생성
- PR merge 후 자동 삭제
- 기준 상태 보존은 branch보다 immutable snapshot descriptor/tag 우선
