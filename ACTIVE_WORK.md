## Dryad image join gate — 2026-09-18

- Datasheet audit is canonical on main: 1,611 fruit IDs, 60 footer rows excluded, 1,571 usable with-calyx primary targets, 40 primary-target missing rows excluded.
- Current workstream: `feat/dryad-image-join-audit` / PR #42.
- Actual authenticated remote validation completed for ZIP metadata access:
  - 7/7 `Pictures_*.zip` central directories read successfully with HTTP Range.
  - `full_archive_download_performed=false`.
  - actual published image entries observed: 12,062.
  - filename→datasheet fruit-ID matching: 12,062 / 12,062.
  - unmatched filenames: 0.
  - ambiguous filenames: 0.
- Therefore the parser/range transport is validated; the remaining issue is published-photo coverage, not filename parsing.
- The original blanket expectation `1,611 × 22 = 35,442 published files` is not treated as an acceptance invariant until the datasheet `Photo` field and actual per-fruit view-count distribution are reconciled.
- Next diagnostic (schema v2): audit datasheet `Photo` values, full per-fruit view-count distribution, complete/partial/overcomplete fruit counts, and overlap with the 1,571 primary-weight candidates.
- Reuse policy: if datasheet SHA-256 + 7 picture archive manifest identities + image-join audit schema version are unchanged, reuse verified image-join audit with no repeat ZIP Range requests.
- Schema v2 intentionally invalidates the prior v1 image-join cache once, so the new coverage diagnostics require one metadata-only Range refresh; no image bodies are downloaded.
- Safety: if Dryad does not honor HTTP Range, abort; never silently fall back to downloading the ~39.24 GB picture archives.
- No raw image bytes are committed.

# Nongtori Active Work Registry


## Environment contract refreeze — 2026-09-18

- TORI 공통 canonical local env: `.env.example`(Git 추적) + `.env.local`(실제 로컬 값, Git 제외).
- Cloudflare runtime resource binding은 `DB`(D1), `FILES`(R2)로 별도 관리하며 문자열 env로 취급하지 않는다.
- Dryad 로컬 연구 secret은 `DRYAD_CLIENT_ID` + `DRYAD_CLIENT_SECRET`; acquisition helper가 access token을 자동 발급한다. `DRYAD_TOKEN`은 임시 override만 허용.
- legacy `.dev.vars` 기준과 과도한 `.env*` ignore는 제거했다.
- machine-readable contract: `configs/environment-contract.json`; human contract: `docs/ENVIRONMENT_VARIABLES.md`.
- Data Pipeline CI는 credential-flow 변경 기준 PASS.

## Branch cleanup — 2026-09-18

Current remote branch state after cleanup:

- `main`: canonical
- `feat/ripeness-v010-convnext-tiny`: KEEP — PR #26 open draft, experiment result not yet recorded
- `feat/ripeness-v009-ordinal-head`: DELETE — PR #25 closed, rejected result preserved on main
- `fix/dryad-oauth-credential-flow`: DELETE — PR #40 closed/unmerged, superseded by newer main implementation
- `exp/ripeness-v003-patience`: MERGED + AUTO-DELETED — PR #27 squash merged as `6d4837f`

Branch deletion for the two DELETE entries is pending only because the connected GitHub tool does not expose remote branch deletion.

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
| Pest scouting state/history V1 | `main`, PR #28~#31 + 2026-09-17 refreeze | MERGED / CANONICAL | actual browser/mobile visual acceptance |
| Pest scouting operations V2 | `main`, PR #32 | MERGED / IMPLEMENTED | 실제 현장 데이터로 freshness/종료 정책 calibration |
| Field data readiness v001 | existing workstream | IN_PROGRESS | readiness validator + tests → PR/CI → merge |
| Ripeness further tuning | PR #26 / `feat/ripeness-v010-convnext-tiny` | PAUSED / RESULT_PENDING | field/photo/video + label freeze 후 successor snapshot에서 재개; V009 rejected result는 main에 보존 |
| Dryad Weight Estimation V1 | `main` + PR #42 | DATASHEET_AUDITED / REMOTE_JOIN_TRANSPORT_VERIFIED / PHOTO_SUBSET_REVIEW | schema-v2 coverage audit → usable photo×weight candidate freeze → snapshot gate |
| Environment / deployment contract | `main` | CANONICAL / CLOUDFLARE_TARGET | D1/R2 bindings + capability secrets만 유지; 미사용 키 선제 추가 금지 |

## Pest scouting canonical state

Current runtime is stateful and location-history based.

Implemented canonical behavior:

- 동일/최근 확인 패턴은 observation은 저장하고 반복 alert는 억제
- 새 anomaly / 악화 / spatial spread / post-treatment rebound는 재알림 가능
- `NO_VISIBLE_EVIDENCE != MITE_NEGATIVE`
- 현장 점검 원본은 append-only, 잘못 누른 입력은 `REPLACE` / `VOID` correction event로 정정
- `RESOLVED`는 명시적 종료만 허용하며 방제 자체가 자동 종료를 의미하지 않음
- RESOLVED 뒤 새 anomaly는 새 case로 생성하고 이전 case와 recurrence link 유지
- field-check freshness는 versioned policy이며 calibration 전 duration 숫자를 임의 고정하지 않음
- capture session / frame / location scope mismatch observation은 저장 거부
- 사람 입력이 없어도 observation/risk lifecycle은 계속 동작하며 미입력을 normal/negative로 변환하지 않음
- 상태 enum과 실제 병해충 대상은 분리: `CONFIRMED`는 workflow 상태이고 실제 대상은 `primary_issue_code`/finding이 담당
- 응애는 첫 automatic scouting target일 뿐 병해충 관리 domain 전체를 응애 전용으로 만들지 않음
- 위치 목표 계약은 `farm_id + spatial_unit_id`; 기존 house/bed/zone runtime은 compatibility layer로 유지
- 농가 공간구조는 `HOUSE/FACILITY/SECTION/BLOCK/BED/ROW/ZONE/CUSTOM` 가변 SpatialUnit hierarchy를 목표로 함
- destructive spatial migration은 포트폴리오 V1 완료 조건이 아니며 별도 migration으로 수행
- 담당자 수동배정/작업 스케줄 최적화/로봇 waypoint/자동방제는 V1 기본 흐름에서 제외

### 2026-09-17 UI refreeze implementation

Main direct commits (branch budget가 이미 full이라 기존 unrelated branch 재사용/삭제 없이 canonical pest workstream 후속으로 반영):

- `272a6e9` — scouting locations API에 latest humidity/thermal context, active-case observation count, display location projection 추가
- `ab808c0` — `ScoutingQueue`를 목록 summary → 선택 상세 구조로 변경
- `179b06f` — desktop/mobile list-detail responsive CSS
- `f0e5553` — status/issue 분리, summary/detail, concise action wording UI regression test 갱신

UX canonical:

```text
병해충 관리
→ 오늘 확인할 구역 목록
→ 행 클릭
→ 구역/CASE 상세
   - 탐지 후보
   - 습도
   - 잎 온도 차
   - 관측 횟수
   - 최근 변화/이력
→ 필요 시 현장 확인 결과 기록
→ 필요 시 별도 조치 기록
```

목록은 `어디를 먼저 볼지`, 상세는 `왜 확인해야 하는지 + 선택적 기록`을 담당한다.
목록 행마다 현장확인/방제/종료 입력 UI를 펼치지 않는다.

농민용 표현은 모델 내부 용어보다 관측값을 우선한다.
예:

```text
습도 43%
잎 온도 +1.8℃
관측 3회
```

`습도 관리 실패`, `thermal anomaly high` 같은 책임/인과 단정 또는 개발자 용어는 기본 UI에서 사용하지 않는다.

Canonical docs:

- `docs/PEST_SCOUTING_STATE_DESIGN.md`
- `docs/PEST_SCOUTING_DB_SCHEMA_V1.md`
- `docs/PEST_SCOUTING_OPERATIONS_V2.md`
- `docs/PEST_SCOUTING_UI_V1_CONTRACT.md`
- `docs/MULTI_FARM_DATA_MODEL.md`
- `docs/PROJECT_SCOPE.md`

Validation performed for 2026-09-17 refreeze:

- updated TS/TSX files: local TypeScript transpile syntax diagnostics = 0
- new scouting-locations SQL projection: representative SQLite schema에서 query parse/execute 확인
- UI regression test source updated
- GitHub PR-based workflow CI: **NOT RUN** (direct main updates; workflow is pull_request-triggered)
- full repository `npm run test:workflows`: **NOT RUN in this session**
- lint/build: **NOT RUN in this session**
- browser/mobile actual rendering/interaction visual acceptance: **NOT RUN**

따라서 코드 반영은 완료했지만 최종 visual acceptance/PASS를 주장하지 않는다.

Remaining validation / calibration:

- actual browser/mobile visual acceptance
- full workflow tests + lint/build on current main
- latest observation values가 실제 현장 payload에서 의도대로 표시되는지 runtime 검증
- SpatialUnit migration 설계/구현은 별도 scoped workstream에서만 수행
- field-derived freshness calibration
- field-derived case resolution automation criteria (if ever enabled)
- irregular-longitudinal early-warning performance validation

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

Current state must be resolved from the actual existing branch/workstream before writing new changes. Do not create a duplicate branch merely from this section.

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
- no next ripeness production claim before successor snapshot freeze.

## 다음 canonical 순서

1. 현재 pest scouting main의 workflow tests/lint/build + browser/mobile visual acceptance.
2. Field readiness current workstream 상태를 actual branch/PR 기준으로 재확인 후 중복 없이 진행.
3. 실제 사진/영상 정리를 계속하고 media listing/materialization이 가능해지면 source↔asset match + SHA-256 audit 수행.
4. 대표 field example이 충분해지면 Maturity 0~4 visual annotation guideline versioning.
5. flower / fruit-set / non-fruit 처리와 ambiguous boundary/adjudication rule 확정.
6. video frame sampling / duplicate / Group_ID·session leakage policy 확정.
7. successor immutable snapshot(v002+) 생성.
8. 새 snapshot에서 clean baseline 재측정 후 historical tuning 재사용 여부 결정.

### 2026-09-18 one-command acquisition/audit

Canonical normal command:

```bash
python -m ml.data_pipeline.cli dryad-weight-audit
```

Normal flow:

```text
resolve Dryad API manifest once
→ save public-manifest.json automatically
→ verify existing datasheet.xlsx against exact size/SHA-256
→ reuse if verified / reacquire automatically if stale or corrupt
→ audit real 20-sheet datasheet
→ exclude 60 footer rows
→ retain 1,571 usable with-calyx primary targets
→ reuse image-join-audit.json when immutable source fingerprint is unchanged
→ otherwise inspect all 7 Pictures_*.zip central directories via guarded HTTP Range
→ verify fruit_id ↔ 22-view join
→ save image-join-audit.json with cache identity
```

Default outputs:

```text
data/raw/dryad/DATA-QUAL-002/datasheet.xlsx
data/audit/dryad/DATA-QUAL-002/public-manifest.json
data/audit/dryad/DATA-QUAL-002/datasheet-audit.json
data/audit/dryad/DATA-QUAL-002/image-join-audit.json
```

Optional diagnostics only:

```bash
python -m ml.data_pipeline.cli dryad-manifest
python -m ml.data_pipeline.cli dryad-image-join-audit
```

Safety:
- local credentials only in `.env.local`
- `DRYAD_CLIENT_ID` + `DRYAD_CLIENT_SECRET`; `DRYAD_TOKEN` is optional one-off override
- picture archive join audit must use HTTP Range and refuse full-body fallback
- no raw Dryad images or credentials are committed

### Published Dryad file inventory

Dryad dataset page 기준 확인:

- `datasheet.xlsx`: 128.08 KB 표시
- `Pictures_01.zip ~ Pictures_07.zip`: 7 archives
- picture archive 표시용량 합계: 39.24 GB
- scan archives: 20
- 전체 게시 데이터셋: 89.98 GB

위 용량은 Dryad 웹페이지의 human-readable 표시값이다. immutable snapshot/file identity에는 사용하지 않는다. exact byte size / digest / download link는 `dryad-manifest`가 API manifest에서 받아 저장한 값만 canonical로 사용한다.

## External weight / Dryad status

Canonical source: `DATA-QUAL-002` / UC Davis Dryad `10.25338/B8V308`.

Frozen facts:
- 1,611 individual strawberries, 22 controlled RGB views per fruit
- width / height / shape + weight with and without calyx
- Nongtori primary GT: `weight_with_calyx`
- `weight_without_calyx`: auxiliary analysis only
- split boundary: `FRUIT_ID`; 22 views of one fruit must never cross train/validation/test
- commercial-use candidate under Dryad CC0 policy; final field acceptance still requires Nongtori Seolhyang data

Acquisition state:
- PR #38 added official Dryad API manifest resolution, token-aware file download, cross-host auth stripping, size verification and SHA-256 verification.
- Anonymous metadata/manifest lookup is available.
- Dryad credentials are local-research secrets, not Nongtori runtime deployment secrets.
- Canonical local files are `.env.example` / `.env.local` across TORI projects.
- `DRYAD_CLIENT_ID` + `DRYAD_CLIENT_SECRET` mint a short-lived token automatically; `DRYAD_TOKEN` is optional override only.
- Real `datasheet.xlsx` audit is complete: 1,611 fruit IDs, 60 footer rows excluded, 1,571 usable with-calyx primary targets, 40 primary-target missing rows excluded.

Next gate:
```text
normal one-command dryad-weight-audit
→ manifest save + datasheet verification/reuse
→ completed 1,611-row audit
→ remote picture archive central-directory inventory
→ fruit ID ↔ 22-view join verification
→ WEIGHT-DRYAD-V001 immutable snapshot candidate
→ geometry / RGB weight baselines
```

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
- branch budget가 full이면 unrelated branch를 임의 삭제/재사용하지 않는다.
- PR merge 후 자동 삭제
- 기준 상태 보존은 branch보다 immutable snapshot descriptor/tag 우선

## POLICY_ACK — ChatGPT logical orchestration — 2026-09-18

- Common baseline: `conanbke-ai/Tori_Common_Project@aefeefd5d2871194daeba39dbd6273bead5ef38a`
- tags: `AGENT_ORCHESTRATION,AI_SURFACE,CREDIT,DOCUMENTATION`
- result: `ADOPTED`
- Runtime model: ChatGPT logical roles; no Cursor/plugin installation required.
- Surface rule: Chat/connector first; Codex only for repository-local implementation/build/test; Work only for actual rendered/interactive acceptance; LOCAL_RUNTIME for long GPU workloads where applicable.
- Product-specific contracts in this repository remain authoritative over generic common assumptions.

### ORCHESTRATION_V3_ACK — 2026-09-18
- Common baseline: `conanbke-ai/Tori_Common_Project@aefeefd5d2871194daeba39dbd6273bead5ef38a`
- Added logical gates: Runtime Reliability / AI Output Evaluation.
- Trigger/regression policy: ADOPTED.
- Product runtime code unchanged by this ACK.

### ROUTING_REGRESSION_ACK — 2026-09-18
- Common baseline: `conanbke-ai/Tori_Common_Project@aefeefd5d2871194daeba39dbd6273bead5ef38a`
- Result: `ORCHESTRATION_REGRESSION_PASS` — 15/15 representative scenarios.
- No product runtime code changed by this ACK.
