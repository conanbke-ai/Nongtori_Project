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
| Ripeness V007 + V008 benchmark | `main`, PR #23 | MERGED / BENCHMARK_FROZEN | evidence 유지 |
| Field data readiness v001 | `main`, PR #24 | MERGED | field inventory 정리와 독립적으로 정책 유지 |
| Ripeness V009 ordinal head | `feat/ripeness-v009-ordinal-head` | IN_PROGRESS / DEVELOPMENT BENCHMARK ONLY | downloaded KGCV snapshot에서 screening 실행 |

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

### Benchmark scope

```text
Snapshot      : KGCV-RIPENESS-V001
Role          : development benchmark
Preferred net : EfficientNet-B0
Field/Drive   : NOT USED for V009
Test tuning   : prohibited
Field status  : NOT FIELD VALIDATED
Production    : NOT APPROVED
```

The benchmark freeze still applies to claims: V001~V009 results must never be described as final field performance. However, downloaded-data-only experiments may continue for architecture/loss/head research while field data is organized separately.

## Current active work — V009 ordinal head

Branch: `feat/ripeness-v009-ordinal-head`

Purpose:
- continue experimentation using only the already downloaded/frozen KGCV development snapshot;
- do not depend on Google Drive / field photo-video readiness;
- compare the confirmed EfficientNet-B0 softmax baseline with a structurally ordinal cumulative-threshold head;
- investigate whether M0/M1 adjacent-stage confusion decreases without harming Macro F1 / Ordinal MAE / Kappa or destabilizing M4.

Canonical files:
- `docs/experiments/ripeness/EXP-RIP-009_ORDINAL_HEAD_PLAN.md`
- `ml/ripeness_baseline/screen_ordinal_v009.py`
- `scripts/run_ripeness_v009_gpu.ps1`

### V009 stop condition

1. local RTX 4060 single-seed screening first;
2. validation only; test remains closed;
3. no Drive/field data dependency;
4. no coefficient/threshold sweep;
5. clear regression → REJECT;
6. positive/tied-but-boundary-better signal → paired 3-seed confirmation;
7. field/production claims remain prohibited regardless of benchmark score.

## Field data / label status

Field data is still being organized and is currently **out of scope for V009 training**.

Canonical Google Sheet working guide may continue to describe Maturity `0~4 (Green, White, Turning, Mature, Full)`, but it is not used to reinterpret or relabel `KGCV-RIPENESS-V001`. External benchmark labels remain governed by their frozen normalization/mapping version.

Field-data readiness policy and PR #24 remain useful for the future field snapshot, but do not block downloaded external-data experiments.

## 다음 canonical 순서

1. V009 local GPU screening on `KGCV-RIPENESS-V001`.
2. Compare Macro F1 / M1 F1 / Ordinal MAE / Weighted Kappa / confusion matrix / M0↔M1 transitions.
3. If positive, paired 3-seed confirmation under the same frozen snapshot.
4. If rejected, record rejection and choose the next evidence-grounded development-benchmark experiment.
5. Separately continue field photo/video/Sheet organization without mixing field WIP into the benchmark.
6. When field data/labels are mature enough, create a successor field-inclusive snapshot and restart clean baseline acceptance there.

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
