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
| Ripeness V007 + V008 benchmark | `main`, PR #23 | MERGED / BENCHMARK_FROZEN | field/data-label successor snapshot 대기 |
| Field data readiness v001 | `feat/field-data-readiness-v001` | IN_PROGRESS | readiness validator + tests → PR/CI → merge |
| Ripeness further tuning | none | PAUSED | field/photo/video + label freeze 후 successor snapshot에서 재개 |

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

### Status

```text
Snapshot      : KGCV-RIPENESS-V001
Role          : development benchmark
Preferred net : EfficientNet-B0
Test tuning   : prohibited
Field status  : NOT FIELD VALIDATED
Production    : NOT APPROVED
```

The current experiment line is frozen in `docs/RIPENESS_BENCHMARK_FREEZE_20260915.md`.

## Field data / label status

Canonical Google Sheet: `딸기_프로젝트`

Observed current source structure:
- tabs: `컬럼정보`, `농가_딸기데이터`, `농가_베드길이`
- field columns include `ID`, `Group_ID`, `Original_No`, `Farm`, `Zone`, `Class`, `DataType`, `View_Type`, `Occlusion`, `Maturity`, `Grade`, `Health`, `Final_Name`
- `Maturity` source guide currently describes `0~4 (Green, White, Turning, Mature, Full)`
- this description is **working field metadata guidance**, not yet a frozen visual annotation standard
- existing external-source mapping (`GREEN/WHITE/TURNING/RED_RIPE`) is normalization policy and must not be silently treated as final field-label acceptance criteria

Current field Sheet audit:
- contiguous identified block: ID `0001`~`0110`
- current observed composition: STR `98`, LEF `12`
- rows after `0110` contain WIP/partial records with missing identity/task fields
- formula-generated `Final_Name` may still exist on incomplete rows, so `Final_Name != null` is not an active-row gate
- duplicate/context-reused `Original_No` exists, so `Original_No` alone is not a unique key
- Date vs embedded Original_No timestamp mismatch exists and is warning-only; source is not auto-corrected
- Group_ID groups multiple views and remains a cross-split leakage boundary

Drive source folders confirmed:
- `남자친구농가(M)`
- `응애피해농가(C)` — grouped scope only; canonical stored farm code is never `C`
- `외부플랫폼(U)`

The currently connected Drive listing returned no directly enumerable child media in those grouping folders, so physical field asset materialization/hash audit remains blocked from this session. Do not fabricate file inventory counts.

## Current active work — Field data readiness v001

Branch: `feat/field-data-readiness-v001`

Canonical draft docs/code:
- `docs/FIELD_DATA_READINESS_POLICY.md`
- `docs/FIELD_DATA_READINESS_AUDIT_20260915.md`
- `ml/data_pipeline/field_readiness.py`
- `scripts/audit_field_sheet_readiness.py`
- `tests/test_field_readiness.py`

Readiness states:

```text
READY_METADATA
PARTIAL
INVALID_FOR_TRAINING
TRAINING_READY   # physical media/hash/label/split/snapshot gates까지 모두 통과한 경우만
```

Current stop condition:
- metadata gate can be implemented/tested now;
- `TRAINING_READY` and successor snapshot cannot be claimed until physical media verification and final label policy are available;
- no V009 ripeness training before successor snapshot freeze.

## 다음 canonical 순서

1. Field readiness validator unit test/CI 통과.
2. PR merge 후 metadata readiness gate를 canonical ingestion policy로 승격.
3. 실제 사진/영상 정리를 계속하고 media listing/materialization이 가능해지면 source↔asset match + SHA-256 audit 수행.
4. 대표 field example이 충분해지면 Maturity 0~4 visual annotation guideline versioning.
5. flower / fruit-set / non-fruit 처리와 ambiguous boundary/adjudication rule 확정.
6. video frame sampling / duplicate / Group_ID·session leakage policy 확정.
7. successor immutable snapshot(v002+) 생성.
8. 새 snapshot에서 clean baseline 재측정 후 historical tuning 재사용 여부 결정.

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
