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
| Ripeness Baseline v001 | `feat/ripeness-baseline-v001-run`, PR #17 | REPRODUCED | result 문서 고정 후 merge → failure analysis / candidate optimization |

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

## RIPENESS-BASELINE-V001 reproduced result

- Model: ImageNet-pretrained ResNet-18
- Best epoch: 1
- Best validation Macro F1: `0.9536944102`
- Test Accuracy: `0.9422632794`
- Test Macro F1: `0.9402391674`
- Test Ordinal MAE: `0.0900692841`
- Test Weighted Kappa: `0.9419644636`
- Per-class F1: M0 `0.9368421053` / M1 `0.9023255814` / M4 `0.9815498155`
- Checkpoint SHA-256: `e9a746113d6d28edb481665ae23b59d9bf542dc9f9da3fb7465488cb2aea8a17`
- Run duration: 22m 24s
- Errors: 0
- Result doc: `docs/RIPENESS_BASELINE_V001_RESULT_20260911.md`

Interpretation:
- `REFERENCE → REPRODUCED` 조건 충족
- M1 precision/F1이 상대적으로 약하고 M0→M1 오분류가 주요 실패 패턴
- epoch 1 이후 validation 성능이 지속적으로 개선되지 않아 현재 full fine-tuning LR/schedule이 빠르게 과적합하는 신호
- external KGCV domain + M0/M1/M4만 포함하므로 production reliability / `FIELD_VALIDATED` 주장 금지

## 다음 canonical workstream

```text
PR #17 merge
→ baseline failure analysis
→ small high-value candidate experiments
   - lower LR
   - frozen-head warm-up + gradual unfreeze
   - scheduler
   - stronger efficient backbone comparison
→ validation-only candidate selection
→ frozen test final evaluation
→ 향후 independent FIELD_TEST
```

## Baseline v001 계약

- ResNet-18 ImageNet transfer learning reference
- object crop classification
- classes: Maturity 0 / 1 / 4
- train augmentation only
- valid: early stopping/model selection
- test: configuration freeze 후 최종 평가만
- primary metrics: Macro F1 / Ordinal MAE / Weighted Kappa
- 임의 accuracy 목표값 금지
- field data 미포함이므로 `FIELD_VALIDATED` 주장 금지

## Logging / Observability

- `docs/LOGGING_OBSERVABILITY_STANDARD.md` canonical 적용
- console / run.log: human-readable progress/metric/checkpoint/error 중심
- `events.jsonl`: structured machine-readable detail
- run summary / metrics / checkpoint hash / retry / stack trace 기본 기록
- regression은 R²/MAE/RMSE, classification/ordinal은 task-specific metric을 기본 기록

## Field data 상태

- canonical Farm: `M / C1 / C2 / U`
- Farm scope `C`는 C1+C2 그룹 조회/작업 범위로 허용
- live Sheet active ID row: 110 (STR 98 / LEF 12)
- shared `Original_No` 및 context-conflict 사례 확인
- 현재 Drive source 분류 폴더에 physical field image가 없어 field asset SHA-256/materialization은 대기
- field data가 들어오면 external KGCV snapshot을 덮어쓰지 않고 별도 revision/snapshot으로 관리

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
