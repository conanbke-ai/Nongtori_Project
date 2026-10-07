## WEIGHT existing-data reuse audit — 2026-10-07

- Before new model research, audit unused Dryad geometry+weight supervision outside the strict 524 RGB cohort.
- Source metadata has 1,571 valid with-calyx targets, but only 524 strict exact-22-view RGB-weight fruit.
- New tool: `python -m ml.weight_baseline.geometry_auxiliary_audit_v1`.
- Candidate role is `AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE` only.
- Official train/validation/test membership is not changed.
- Auxiliary fruit must not be treated as RGB training samples when approved RGB assets are absent.
- Next: run the local audit and use the real candidate count to decide whether Geometry V2 augmentation is worthwhile before disagreement/aggregation/model changes.
## WEIGHT development CV protocol V1 — 2026-10-07

- Official `WEIGHT-DRYAD-V001` split remains immutable: train 367 / validation 79 / test 78 FRUIT_ID.
- Validation 79 is a role-specific holdout, not the total weight dataset size.
- The 22 views per fruit remain one FRUIT_ID atomic unit and never count as 22 independent validation samples.
- V002+ method development should use deterministic train-only 5-fold CV before consuming official validation.
- New tool: `python -m ml.weight_baseline.development_cv_v1`.
- Expected five-fold validation sizes for 367 train fruit: 74 / 74 / 73 / 73 / 73.
- Official validation is excluded from inner CV; official test remains locked from successor tuning.
## WEIGHT selective auto-grade evaluator V1 — 2026-10-07

- Added validation-only evaluator for Fusion V001.
- Candidate policy is based on predicted distance to nearest fixed 12/16/22g threshold.
- Reports observed precision, coverage, fallback rate, error count, severe errors, and Wilson 95% lower bound.
- Default target observed precision: 0.99.
- If no candidate meets target with minimum sample count, status is `SELECTIVE_AUTO_GRADE_TARGET_NOT_MET`; no policy is forced.
- Test split is explicitly locked and excluded from successor policy selection.
- Next local step after merge: run Fusion boundary audit and selective auto-grade evaluator, then decide V1 freeze.
## WEIGHT portfolio ML completion scope — 2026-10-07

- V1 completion target is not whole-dataset 99% grade accuracy.
- Product KPI is selective `AUTO_GRADE precision + coverage + fallback rate`.
- Remaining ML V1 work:
  1. Fusion boundary residual audit
  2. validation-based AUTO_GRADE / RE_MEASURE_REQUIRED policy
  3. measured fallback integration verification
  4. Weight ML V1 freeze
- After freeze, priority moves to API/UI/field UX/QA rather than open-ended model tuning.
- Academic extensions (RGB-D/3D, multi-task/ordinal research, probabilistic/conformal uncertainty, large external field validation) are FUTURE/successor scope.
## WEIGHT fusion V001 result freeze — 2026-10-02

- Fusion V001 real execution completed.
- Validation-selected weights: RGB 0.5 + Geometry 0.5.
- Validation:
  - MAE 1.2242g
  - RMSE 1.7285g
  - R² 0.9116
  - grade accuracy 0.8354
  - grade errors 13
  - threshold crossings 13
  - MaxAE 5.8589g
- Frozen test:
  - MAE 0.9792g
  - RMSE 1.6143g
  - R² 0.9456
  - bias -0.0140g
  - grade accuracy 0.8846
  - grade errors 9
  - threshold crossings 10
  - MaxAE 9.3984g
- Decision: `CURRENT_PREFERRED_WEIGHT_ESTIMATOR_BENCHMARK`.
- Test is now locked for successor tuning. Future multi-task/ordinal loss or uncertainty-band selection must use train/validation only.
- Immediate next gate: run fixed-threshold residual audit on `fusion_predictions.csv` before deciding whether boundary-aware multi-task learning is justified.
- Result freeze doc: `docs/WEIGHT_FUSION_V001_RESULT_20261002.md`.

## WEIGHT fusion V001 — 2026-10-02

- Paired test audit supports a controlled fusion experiment:
  - RGB lower absolute error on 44/78 test fruits; Geometry on 34/78.
  - signed residual Pearson 0.0485; absolute-error Pearson 0.5882.
  - diagnostic oracle lower-bound MAE 0.7574g.
- Test evidence is diagnostic only and is not used to select fusion weights.
- Current workstream: `feat/weight-fusion-v001`.
- V001 fusion family is fixed to convex blend `alpha_rgb * RGB + (1-alpha_rgb) * Geometry`.
- Candidate alpha values are fixed at 0.0~1.0 by 0.1.
- Alpha selection uses validation only with lexicographic priority:
  1. grade error count
  2. threshold crossing count
  3. MAE
  4. RMSE
- Test is report-once and excluded from weight selection.
- Regression test guarantees that changing test predictions cannot change selected alpha.
- Canonical design: `docs/WEIGHT_FUSION_BASELINE_V001.md`.

## WEIGHT RGB V001 real result + paired audit — 2026-10-02

- RGB V001 completed on the frozen `WEIGHT-DRYAD-V001` split.
- Best checkpoint: epoch 7, validation fruit MAE 1.5647g.
- Final test:
  - MAE 1.2401g
  - RMSE 2.3446g
  - R² 0.8852
  - bias -0.4192g
  - max absolute error 12.4082g
  - weight-grade accuracy 0.8333
- Geometry V001 comparison on the same test split:
  - MAE 1.4125g
  - RMSE 2.1850g
  - R² 0.9003
  - grade accuracy 0.8205
- Interpretation: RGB improves average absolute error and grade accuracy, but worsens RMSE/R² and creates a larger max-error tail. Do not declare a global winner from MAE alone.
- Current workstream: `feat/weight-paired-residual-audit-v1`.
- Next gate: paired FRUIT_ID residual / threshold-crossing audit before any RGB+Geometry fusion experiment.
- Test remains report-only; paired test diagnostics must not select fusion weights or thresholds.

## Weight runtime provenance V1 — 2026-10-02

- Runtime append-only `fruit_weight_observations` implemented on `feat/runtime-weight-source-v1`.
- Supported provenance: `SENSOR_MEASURED / MANUAL_MEASURED / VISION_ESTIMATED`.
- Resolver priority: SENSOR > MANUAL > VISION; recency only breaks ties within the same source class.
- Public `/api/fruit-weights` POST records manual measured values only; caller-supplied sensor/model provenance is rejected.
- Internal service exposes explicit sensor/vision append operations for future adapters.
- Fixed provisional weight-grade boundaries remain 12/16/22g.
- History is retained; higher-trust weight does not delete lower-trust observations.
- Actual harvester/load-cell device adapter remains NOT CONNECTED.

## Weight estimation product-role refreeze — 2026-10-02

- Portfolio constraint: target harvesting hardware is not fixed, so load-cell availability cannot be assumed.
- Vision weight estimation remains an active capability experiment; it is **not** positioned as a universal replacement for physical weighing.
- Future runtime source priority is frozen as:
  - `SENSOR_MEASURED`
  - `MANUAL_MEASURED`
  - `VISION_ESTIMATED`
- Trusted measured weight must override a vision estimate.
- Current field `Weight_g` remains ground truth. Runtime weight provenance is implemented via append-only `fruit_weight_observations` and `SENSOR_MEASURED / MANUAL_MEASURED / VISION_ESTIMATED` source resolution.
- Fixed 12/16/22g boundaries remain product rules for weight-grade analysis; validation/test must not tune them.
- Weight-model acceptance must include boundary crossings and grade confusion in addition to MAE/RMSE/R².
- Canonical design doc: `docs/WEIGHT_ESTIMATION_PRODUCT_ROLE_V1.md`.
- Current experiment roadmap remains Geometry V001 → RGB V001 → paired residual comparison → optional fusion/multi-task.

## WEIGHT RGB baseline V001 — 2026-09-28

- WEIGHT-DRYAD-V001 is now frozen locally: 524 fruits / 11,528 RGB views.
- Geometry V001 real baseline completed:
  - test MAE 1.4125g
  - test RMSE 2.1850g
  - test R² 0.9003
  - test grade accuracy 0.8205
- Current workstream: `feat/weight-rgb-baseline-v1`.
- RGB training unit is one view; evaluation unit is one FRUIT_ID.
- Each fruit prediction is the mean of exactly 22 view-level predictions.
- Fixed model: EfficientNet-B0 ImageNet pretrained.
- Checkpoint selection: best validation FRUIT_ID-level MAE only.
- Test set is report-once and excluded from tuning.
- Next after real RGB result: geometry-vs-RGB paired comparison on identical fruit test IDs, then optional combined model.

## WEIGHT threshold residual audit V001 — 2026-09-28

- Geometry baseline V001 is merged on main.
- Current workstream: `feat/weight-threshold-residual-audit-v1`.
- Input: `artifacts/weight/geometry-v001/geometry_predictions.csv`.
- Primary prediction column: `linear_width_height_area_pred_g`.
- Fixed Nongtori weight boundaries remain 12g / 16g / 22g.
- Audit measures threshold crossings, grade errors, distance-to-boundary bands, within-2g boundary error rates, and top absolute errors by split.
- Policy is analysis-only: no threshold tuning from validation/test results.
- Next after real audit result: RGB-only weight regression baseline on the same WEIGHT-DRYAD-V001 split.

## WEIGHT geometry baseline V001 — 2026-09-28

- PR #50 merged: WEIGHT-DRYAD-V001 freeze gate is now on main.
- Current workstream: `feat/weight-geometry-baseline-v1`.
- Baseline unit is one `FRUIT_ID`, not one RGB view; the 22 views are not duplicated as geometry regression samples.
- Fixed models: TRAIN_MEAN, LINEAR_WIDTH_HEIGHT, LINEAR_WIDTH_HEIGHT_AREA.
- Primary model is predeclared as LINEAR_WIDTH_HEIGHT_AREA; no validation-driven model selection in V001.
- Metrics: MAE/RMSE/R²/Bias/MaxAE + 12/16/22g grade accuracy/confusion.
- Test split is report-once and must not be used for tuning.
- Execution blocks until an actual frozen `WEIGHT-DRYAD-V001` exists locally.
- Next after real geometry baseline: threshold residual audit → RGB-only baseline → geometry vs RGB comparison → optional combined model.

## Dryad WEIGHT-DRYAD-V001 freeze gate — 2026-09-28

- Next gate implementation is now in progress on `feat/dryad-weight-snapshot-v1`.
- Freeze command: `python -m ml.data_pipeline.cli dryad-freeze-weight-snapshot`.
- Hard prerequisite: materialization manifest must be `STRICT_CANDIDATE_ASSETS_VERIFIED` with exactly 11,528/11,528 verified image rows.
- Freeze re-verifies every local asset SHA-256, enforces 22 views per fruit, loads with-calyx primary target metadata from the Dryad datasheet, and rejects candidate/materialized identity drift.
- Split boundary is strictly `FRUIT_ID`; all 22 views of a fruit stay in one split.
- Snapshot artifacts: `fruit-splits.csv`, `sample-manifest.csv`, `WEIGHT_SNAPSHOT.json`.
- Snapshot records candidate/materialized/datasheet hashes plus deterministic split and asset-row digests.
- Existing snapshot ID is immutable; rerun against an existing `WEIGHT-DRYAD-V001` directory is rejected.
- This code gate does not claim the real snapshot is frozen until local materialization is complete.

## Dryad archive-cache materialization gate — 2026-09-21

- Member-by-member HTTP Range materialization is retired after repeated Dryad HTTP 429 rate limiting.
- Strict candidate remains frozen: 524 fruit IDs / 11,528 images; candidate row identity is unchanged.
- Canonical materialization mode: `SEQUENTIAL_ARCHIVE_CACHE` (PR #49 workstream).
- Process one `Pictures_*.zip` at a time:
  - resumable `.part` archive download;
  - official exact byte-size + SHA-256 verification;
  - extract strict candidate members only;
  - member size + CRC32 + SHA-256 verification;
  - delete archive after extraction by default;
  - `--keep-archives` is diagnostic/optional only.
- Existing verified extracted members are reused, so interrupted reruns skip finished assets.
- Peak transient archive storage is bounded to one picture ZIP rather than all seven.
- Next gate after 11,528/11,528 verification: FRUIT_ID atomic split → WEIGHT-DRYAD-V001.

## Dryad selective materialization gate — 2026-09-21

- Upstream strict candidate manifest is merged on `main`: 524 fruit IDs / 11,528 images.
- Current workstream: `feat/dryad-selective-materialization`.
- Materialization is selective-only through HTTP Range backed ZIP reads; full picture ZIP download fallback remains forbidden.
- Existing local members are verified by exact size + CRC32 + SHA-256 and reused without member download.
- Missing/corrupt members are re-materialized atomically via `.part` replacement.
- Per-image SHA-256 is persisted to `strict-materialized-assets.json`.
- Checkpoint manifest is written during progress; interrupted runs safely re-adopt already verified local files.
- ZIP member paths are validated against absolute/path-traversal writes.
- Next gate after real local completion: FRUIT_ID-grouped immutable train/valid/test split + WEIGHT-DRYAD-V001 snapshot freeze.

## Dryad strict candidate asset gate — 2026-09-18

- Canonical strict policy: `VALID_WITH_CALYX_WEIGHT_AND_EXACTLY_22_PUBLISHED_VIEWS`.
- Strict candidate: 524 fruit IDs / 11,528 RGB images.
- Current workstream: `feat/dryad-strict-candidate-manifest`.
- Candidate manifest records archive path/digest/file-id, member filename, uncompressed/compressed size, compression method, CRC32 and ZIP local-header offset.
- Candidate manifest cache identity derives from the verified image-join source fingerprint + policy/schema version.
- If candidate manifest fingerprint matches, reuse it with no repeat ZIP central-directory Range requests.
- First manifest build requires one metadata-only central-directory pass because prior audit cache did not persist member filenames/offsets.
- No image bodies are downloaded at manifest stage.
- Materialization stage now uses one verified picture archive at a time because member-level Range requests triggered sustained Dryad 429 limits.
- It skips already-present files after hash verification, resumes interrupted archive downloads via `.part`, extracts only strict candidates, deletes the archive by default, and produces per-image SHA-256 before immutable snapshot freeze.
- Split boundary remains FRUIT_ID.

## Dryad image join gate — 2026-09-18

- Datasheet audit canonical facts:
  - 1,611 fruit IDs.
  - 60 footer rows excluded.
  - 1,571 usable with-calyx primary targets.
  - 40 primary-target missing rows excluded.
- Real remote picture validation:
  - 7/7 picture archive central directories read by HTTP Range.
  - full archive download not performed.
  - 12,062 published image entries observed.
  - filename→fruit-ID matches: 12,062 / 12,062.
  - unmatched: 0; ambiguous: 0.
- Datasheet Photo reconciliation:
  - Photo=NO: 1,062 fruits, all zero published images.
  - Photo=YES: 549 fruits, all have published images.
  - among Photo=YES: 541 exact-22, 7 partial, 1 overcomplete.
- Weight×RGB overlap:
  - primary with-calyx candidates: 1,571 fruits.
  - primary candidates with any published picture: 532.
  - primary candidates with exact 22 published views: 524.
  - strict RGB-weight candidate: 524 fruits / 11,528 images.
  - split boundary remains FRUIT_ID; the 22 views of one fruit must never cross train/validation/test.
- Acceptance status: PUBLISHED_SUBSET_VERIFIED_WITH_VIEW_EXCEPTIONS.
- Strict snapshot policy: VALID_WITH_CALYX_WEIGHT_AND_EXACTLY_22_PUBLISHED_VIEWS.
- Partial/overcomplete photo fruits remain review-only and are excluded from the strict snapshot candidate.
- Cache: schema-v2 source fingerprint stays valid; final acceptance derivation is local-only and does not require another ZIP Range refresh.
- Safety: no full multi-GB picture archive download; raw images/credentials never committed.

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
| Dryad Weight Estimation V1 | `main` + strict-manifest workstream | STRICT_524_FRUIT_CANDIDATE_FROZEN / ASSET_MANIFEST_IN_PROGRESS | member manifest → selective resumable materialization → per-image SHA-256 → FRUIT_ID split → WEIGHT-DRYAD-V001 |
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

- Common baseline: `conanbke-ai/Tori_Common_Project@943b567e7740d72727c45ba4c03d267e99dc4596`
- tags: `AGENT_ORCHESTRATION,AI_SURFACE,CREDIT,DOCUMENTATION`
- result: `ADOPTED`
- Runtime model: ChatGPT logical roles; no Cursor/plugin installation required.
- Surface rule: Chat/connector first; Codex only for repository-local implementation/build/test; Work only for actual rendered/interactive acceptance; LOCAL_RUNTIME for long GPU workloads where applicable.
- Product-specific contracts in this repository remain authoritative over generic common assumptions.

### ORCHESTRATION_V3_ACK — 2026-09-18
- Common baseline: `conanbke-ai/Tori_Common_Project@943b567e7740d72727c45ba4c03d267e99dc4596`
- Added logical gates: Runtime Reliability / AI Output Evaluation.
- Trigger/regression policy: ADOPTED.
- Product runtime code unchanged by this ACK.

### ROUTING_REGRESSION_ACK — 2026-09-18
- Common baseline: `conanbke-ai/Tori_Common_Project@943b567e7740d72727c45ba4c03d267e99dc4596`
- Result: `ORCHESTRATION_REGRESSION_PASS` — 15/15 representative scenarios.
- No product runtime code changed by this ACK.

### PRODUCT_FLOW_QA_ACK — 2026-09-23
- Common baseline: `conanbke-ai/Tori_Common_Project@943b567e7740d72727c45ba4c03d267e99dc4596`
- Result: `ADOPTED`
- User-facing changes require PRE_IMPLEMENTATION_FLOW_QA and PRE_COMPLETION_FLOW_QA; implementation may be reordered/trimmed when the current journey is unnecessarily difficult or risky.
- Product runtime code unchanged by this ACK.

### PROFESSIONAL_QA_V5_ACK — 2026-09-23
- Common baseline: `conanbke-ai/Tori_Common_Project@943b567e7740d72727c45ba4c03d267e99dc4596`
- Result: `ADOPTED`
- Non-trivial feature lifecycle: QA PRECHECK -> implementation -> Functional/Regression -> selected specialist QA -> Accessibility/Compatibility/Visual as applicable -> regression -> QA exit -> Acceptance.
- User-facing flows keep mandatory Product Flow QA before implementation and completion.
- Product runtime code unchanged by this ACK.
