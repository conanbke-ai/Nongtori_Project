# ICRA/Dyson Weight Reference Pipeline V1

Status: **NON_COMMERCIAL_REFERENCE / ACQUISITION_AUDIT_READY**

## 1. Source

Official repository:

- `https://github.com/imanlab/strawberry-pp-w-r-dataset`
- Dataset #1 public Google Drive:
  `https://drive.google.com/drive/folders/1meEKYLgdQpUgkpeqM6VgzHmJg0gNTCx0?usp=sharing`

The official repository describes Dataset #1 as four sub-folders containing sample groups with common file stems.

Recognized roles:

```text
*_rgb.png         RGB
*_bgremoved.png   RGB without background
*_label.npy       weight annotation
*_rdepth.npy      raw depth
*_pc.ply          point cloud
*_odepth.png      colorized depth
*_pdepth.png      colorized depth
```

## 2. License isolation

Official license: **CC-BY-NC-SA**.

Nongtori role:

```text
dataset_role = NON_COMMERCIAL_REFERENCE
commercial_training_ready = false
canonical_commercial_training_merge_allowed = false
dryad_snapshot_auto_merge_allowed = false
```

The dataset may be used for non-commercial research/reference evaluation. It must not be silently merged into the commercial/canonical Weight training snapshot.

Separate permission is required before any commercial training use.

## 3. Acquisition

Optional dependency:

```bash
python -m pip install gdown
```

Command:

```bash
python -m ml.data_pipeline.cli dyson-acquire
```

Default paths:

```text
raw:
data/external/icra-dyson/

audit:
data/audit/icra-dyson/
```

Acquisition uses the public Google Drive folder through `gdown`.

Behavior:

- existing local ZIP archives are detected before download;
- `gdown --continue` is used for interrupted runs;
- reruns are safe and may reuse completed local archives;
- the official Dataset #1 payload is expected as exactly `1.zip`~`4.zip`;
- each ZIP is CRC-checked, path-traversal/symlink members are rejected, and members are materialized under `data/external/icra-dyson/extracted/<archive>/`;
- macOS archive metadata (`__MACOSX`, `._*`, `.DS_Store`) is excluded from materialization/audit and never treated as a dataset sample;
- interrupted reruns reuse extracted members only when both size and CRC match the ZIP metadata;
- extraction uses atomic `.part` replacement;
- `extraction-manifest.json` records archive SHA-256, member counts, reuse counts, and uncompressed bytes;
- Google Drive quota/access failures are reported as BLOCKED;
- acquisition completion does not imply weight/RGB join validity;
- raw files remain Git-ignored.

Output:

```text
data/audit/icra-dyson/acquisition-manifest.json
```

## 4. Audit

Command:

```bash
python -m ml.data_pipeline.cli dyson-audit
```

The audit recursively scans downloaded files and removes only the known suffix from each filename to derive a canonical sample stem.

Example:

```text
strawberry_dyson_lincoln_tbd__002_1_rgb.png
strawberry_dyson_lincoln_tbd__002_1_label.npy

→ canonical sample stem:
strawberry_dyson_lincoln_tbd__002_1
```

Minimum reference pair:

```text
RGB + weight label
```

The audit does not assume that one `*_label.npy` file is a scalar.

For each label file it inspects:

- NumPy dtype
- shape
- ndim
- scalar vs vector/array
- number of weight items
- finite/non-finite values
- positive/non-positive values
- min/max

This is required because one image may contain multiple annotated strawberries.

## 5. Provenance

Audit outputs:

```text
data/audit/icra-dyson/
├─ acquisition-manifest.json
├─ extraction-manifest.json
├─ file-manifest.csv
├─ sample-inventory.csv
├─ weight-label-audit.json
└─ join-audit.json
```

`file-manifest.csv` records for every recognized sample file:

- sample stem
- semantic role
- relative path
- byte size
- SHA-256

`sample-inventory.csv` records sample-level role availability and the main RGB/weight/depth/point-cloud paths and hashes.

## 6. Acceptance

Reference-ready status:

```text
DYSON_NON_COMMERCIAL_REFERENCE_READY
```

requires:

- at least one exact RGB+weight pair;
- no missing RGB among recognized sample stems;
- no missing weight label;
- no duplicate semantic role per sample stem;
- no NaN/Inf weight values;
- no non-positive weight values.

Otherwise:

```text
DYSON_REFERENCE_AUDIT_WITH_EXCEPTIONS
```

The audit result never changes:

```text
commercial_training_ready = false
```

## 7. What happens after the first real audit

Do not infer fruit count from image count.

After the first real download, inspect:

- `total_sample_stems`
- `exact_rgb_weight_matched_count`
- `weight_label_summary.shape_counts`
- `total_weight_annotations`
- missing/duplicate counts
- RGB/depth/point-cloud availability

Only after the actual `label.npy` structure is known can Nongtori decide whether this dataset is useful as:

- RGB weight reference;
- RGB-D weight reference;
- point-cloud/3D research reference;
- external non-commercial benchmark.

## 8. Explicit non-goals

V1 does not:

- merge Dyson data into `WEIGHT-DRYAD-V001`;
- create train/validation/test splits for commercial training;
- modify weight labels;
- convert a vector weight label into a scalar without verified identity semantics;
- claim commercial-use permission;
- alter existing Dryad artifacts.


### Existing extracted metadata

If an earlier run already materialized `__MACOSX` or AppleDouble files, they do not need to be deleted before rerunning `dyson-audit`; the audit ignores them explicitly. A later `dyson-acquire` rerun will skip those metadata members when materializing archives.


## 9. Real schema audit findings — 2026-10-08

The first full local audit found that the dataset cannot be interpreted as one scalar weight per RGB file.

Observed before parser correction:

- 22,122 files including four source ZIPs
- 11,336 macOS metadata files ignored
- 1,018 basename-only stems
- 1,619 RGB files
- 1,504 `*_label.npy` files
- label shapes include `(N,3)` and `(N,7)`
- 3,406 numeric values were previously misreported as "weight items"
- identical basenames occur across different archive/subfolder partitions

Therefore V2 audit policy is:

1. canonical sample identity = relative parent path + filename stem, not basename alone;
2. identical basenames in different Dataset #1 partitions are not duplicate samples;
3. `label.npy` is treated as an unresolved numeric matrix until column semantics are verified;
4. report row count, column count, per-column statistics, and representative rows;
5. do not call `array.size` a weight-annotation count;
6. compare observed counts against the paper's published Dataset-1 reference counts, but do not force the raw files to match those numbers without verified mapping;
7. status remains `DYSON_REFERENCE_SCHEMA_REVIEW_REQUIRED` while multi-column label semantics are unresolved.

This preserves the source data exactly and prevents an arbitrary column from being declared the weight target.


## 10. Scene/view schema hypothesis gate — 2026-10-08

The corrected V2 audit found:

- 1,619 partition-aware RGB sample IDs
- 1,504 RGB+label pairs
- 1,918 total label rows
- label widths: 3 / 6 / 7
- 7-column examples such as:
  `[1, 17.5, 37.76, 34.45, 32.06, 293, 179]`
- matching scene views where `_1` contains `(N,7)` and `_2`, `_3` contain `(N,3)`

This strongly suggests a scene-level design in which one view contains full berry attributes while companion views carry instance ID + 2D coordinates.

The next audit therefore verifies, without mutating source data:

1. scene identity by removing the terminal `_<view>` suffix;
2. presence of views 1/2/3 per scene;
3. instance-ID consistency between the full-label view and coordinate-only views;
4. independent full-label row count;
5. candidate weight column statistics for 7-column rows;
6. SHA-256 uniqueness of RGB files to explain the local 1,619 vs paper 1,588 image count.

The 7-column second field is only a **weight-column candidate** until the scene audit passes. It is not silently promoted into a training target.


## 11. Exception audit gate — 2026-10-08

Observed local scene-schema summary:

- scene_count = 542
- three_view_scene_count = 535
- full_label_scene_count = 502
- full_label_row_count = 641
- candidate 7-column weight rows = 637
- 3-column companion rows = 1,275
- instance-ID matched scenes = 496
- instance-ID mismatched scenes = 6
- RGB files = 1,619
- unique RGB SHA-256 = 1,619
- RGB duplicate files = 0

Important arithmetic:

- 641 full-label rows - 637 7-column rows = 4 exceptional 6-column rows
- local scenes 542 - paper sets 532 = +10 scenes
- local RGB 1,619 - paper images 1,588 = +31 RGB files
- because all 1,619 RGB hashes are unique, the +31 are not byte-for-byte duplicates

New artifact:

`data/audit/icra-dyson/scene-schema-exceptions.json`

It records:

- all instance-ID mismatch scenes
- incomplete 3-view scenes
- scenes missing a full-label view
- all 6-column exceptional rows
- partition-level sample/RGB/label/JSON counts
- local-vs-paper count deltas

Do not freeze the 637-row candidate cohort until these exceptions are reviewed.


## 12. Strict physical-berry manifest — 2026-10-08

Exception review supports a conservative physical-berry cohort.

Policy:

- include only full-label rows with exactly 7 columns;
- interpret them as `[instance_id, weight_g, dimension_1, dimension_2, dimension_3, center_x, center_y]`;
- do not auto-recover 6-column rows;
- do not require all three RGB views for berry inclusion;
- record whichever views contain the same berry instance ID;
- keep annotation-only partition 2 out of the weight cohort;
- keep all outputs `NON_COMMERCIAL_REFERENCE`.

Artifacts:

```text
data/audit/icra-dyson/
├─ physical-berry-manifest.csv
└─ physical-berry-manifest.json
```

The CSV stores one row per strict physical berry with:

- scene ID / berry instance ID
- measured weight candidate in grams
- three dimensions
- full-label center coordinate
- view 1/2/3 RGB path and center coordinate when that berry is visible
- matched-view count
- schema/provenance/license guard

Current expected strict count from the observed local package is 637 berries. The four 6-column rows remain excluded pending separate semantic proof.


## 13. Immutable reference freeze

After the real strict manifest is verified, freeze it with:

```bash
python -m ml.data_pipeline.cli dyson-freeze-reference
```

Default snapshot:

`data/snapshots/DYSON-REFERENCE-V001/`

Artifacts:

- `REFERENCE_SNAPSHOT.json`
- `physical-berry-manifest.csv`
- `rgb-asset-manifest.csv`

The freeze revalidates the strict berry count (637 by default), re-hashes every referenced RGB asset, records upstream audit hashes, and refuses to overwrite an existing snapshot ID.

This is a **NON_COMMERCIAL_REFERENCE** snapshot, not a training snapshot. It creates no train/validation/test split and preserves `commercial_training_ready=false`.


## 14. Official berry annotation acquisition/schema audit

The official repository separately publishes `annotations/dyson_annotations.zip` and states that every image has a JSON annotation containing bounding boxes, keypoints, and ripe/unripe category information.

Before joining those annotations to the frozen 637-berry reference cohort, Nongtori uses a schema-discovery gate rather than assuming field names.

Commands:

```bash
python -m ml.data_pipeline.cli dyson-annotations-acquire
python -m ml.data_pipeline.cli dyson-annotations-audit
```

The acquisition gate verifies the official GitHub archive identity:

- expected Git blob SHA-1: `6f9263b45f9dc7c2456cbab3fbc52930136df105`
- expected archive size: `5,222,590` bytes
- safe ZIP paths only; symlinks/path traversal rejected
- macOS metadata and non-JSON members excluded from the schema corpus

The audit reports actual JSON structure without promoting guessed fields:

- JSON count and parse errors
- top-level types/keysets
- frequently observed keys
- candidate bbox/keypoint/category/image/id keys
- list-of-object keysets
- image-reference strings
- representative documents

Artifacts:

```text
data/audit/icra-dyson-annotations/
├─ annotation-acquisition-manifest.json
├─ annotation-inventory.csv
└─ annotation-schema-audit.json
```

Only after reviewing the real schema should a berry-instance → bbox join and crop materialization be implemented.


## 15. Berry-instance to official bbox join audit

After schema discovery, the next read-only gate joins the immutable physical-berry reference rows to official per-image annotation objects.

Command:

```bash
python -m ml.data_pipeline.cli dyson-annotation-join-audit
```

Default inputs:

```text
snapshot:
data/snapshots/DYSON-REFERENCE-V001/

official annotations:
data/external/icra-dyson-annotations/extracted/

audit output:
data/audit/icra-dyson-annotations/
```

Canonical image mapping is path-aware:

```text
extracted/<archive>/<partition>/<scene>/<stem>_<view>_rgb.png
→
dyson_annotations/<partition>/<scene>/<stem>_<view>_keypoint.json
```

The join never uses annotation-list order as berry identity. For each frozen berry/view:

1. read the source `view_N_x/view_N_y` center from the immutable physical-berry manifest;
2. load the exact official annotation JSON resolved from the partition-aware RGB path;
3. validate each bbox as finite absolute XYXY with `x2 > x1` and `y2 > y1`;
4. count annotation bboxes containing the frozen source center;
5. assign only when exactly one valid bbox contains that center.

Statuses:

```text
UNIQUE_GEOMETRIC_MATCH
NO_OBJECT_MATCH
AMBIGUOUS_MATCH
NO_ANNOTATION_IMAGE
INVALID_SOURCE_CENTER
INVALID_BBOX
```

Safety rules:

- no nearest-bbox fallback;
- no selection by category;
- no automatic choice among overlapping boxes;
- no bbox expansion/clamping;
- no fabricated annotation;
- category IDs remain numeric until source semantics are independently verified;
- Dyson remains `NON_COMMERCIAL_REFERENCE` and `commercial_training_ready=false`.

Artifacts:

```text
data/audit/icra-dyson-annotations/
├─ berry-annotation-join.csv
└─ berry-annotation-join-audit.json
```

Schema counts are computed once per unique annotation JSON/object rather than once per physical berry, preventing repeat-count inflation.

The next crop-materialization gate may use only rows whose status is `UNIQUE_GEOMETRIC_MATCH`. Source exceptions remain explicit and are not repaired automatically.


## 16. Berry crop materialization

After the annotation join audit is reviewed, materialize berry-level RGB crops with:

```bash
python -m ml.data_pipeline.cli dyson-materialize-berry-crops
```

Eligibility is strict:

```text
join_status == UNIQUE_GEOMETRIC_MATCH
```

All other join rows remain excluded. No nearest-object fallback or ambiguous selection is allowed.

Default paths:

```text
source RGB:
data/external/icra-dyson/

join audit:
data/audit/icra-dyson-annotations/

crop output:
data/external/icra-dyson-berry-crops/

crop audit:
data/audit/icra-dyson-berry-crops/
```

Crop rule:

- input bbox semantics: absolute XYXY;
- pixel left/top = floor(x1/y1);
- pixel right/bottom = ceil(x2/y2);
- source image bounds are checked during materialization;
- out-of-bounds bbox is reported and never clamped;
- source RGB files are read-only;
- reruns reuse existing crop files.

Artifacts:

```text
data/audit/icra-dyson-berry-crops/
├─ berry-crop-manifest.csv
└─ berry-crop-audit.json
```

The crop manifest preserves:

- berry / scene / view identity;
- frozen weight and three physical dimensions;
- source RGB path and SHA-256;
- source center;
- source bbox and integer crop box;
- numeric category ID;
- crop path and SHA-256;
- NON_COMMERCIAL_REFERENCE provenance guard.

These crops are external reference inputs only. They do not alter `DYSON-REFERENCE-V001`, do not create a commercial split, and must not be merged into Dryad/canonical training.


## 17. External RGB V001 generalization benchmark

After berry crops are materialized, evaluate the already-trained Dryad RGB V001 checkpoint without any retraining:

```bash
python -m ml.weight_baseline.dyson_external_rgb_v001
```

Default model input:

```text
artifacts/weight/rgb-v001/best.pt
artifacts/weight/rgb-v001/rgb_baseline.json
```

Default Dyson input:

```text
data/audit/icra-dyson-berry-crops/berry-crop-manifest.csv
data/external/icra-dyson-berry-crops/
```

Policy:

- only successful materialized/reused crops are evaluated;
- crop SHA-256 is verified before inference;
- the Dryad V001 checkpoint is not retrained or tuned;
- no Dyson threshold/model/aggregation selection is performed;
- RGB V001 eval transform is preserved exactly;
- physical-berry prediction = arithmetic mean of available successful crop-view predictions;
- Dyson remains an external non-commercial reference dataset.

Outputs:

```text
artifacts/weight/dyson-external-rgb-v001/
├─ dyson_rgb_view_predictions.csv
├─ dyson_rgb_berry_predictions.csv
└─ dyson_external_rgb_benchmark.json
```

Reported metrics include MAE, RMSE, R², bias, max absolute error, fixed 12/16/22g grade accuracy/error count, and confusion. These metrics describe cross-dataset generalization only; they must not be used to retune the frozen Dryad V001 model.


## 18. RGB V001 domain-shift audit

When the frozen Dryad RGB V001 model performs poorly on Dyson, quantify the target-distribution shift before proposing any successor model.

Command:

```bash
python -m ml.weight_baseline.dyson_rgb_domain_shift_audit_v1
```

Inputs:

```text
data/snapshots/WEIGHT-DRYAD-V001/fruit-splits.csv
artifacts/weight/dyson-external-rgb-v001/dyson_rgb_berry_predictions.csv
```

The audit compares Dryad test actual weights against Dyson actual weights using:

- min / q05 / q25 / median / q75 / q95 / max;
- mean and population standard deviation;
- fixed Nongtori 12/16/22g grade counts and proportions;
- total-variation distance between grade distributions.

It also reports Dyson RGB V001 error metrics by actual-weight band:

```text
<12g
12–<16g
16–<22g
>=22g
```

This audit is descriptive only. It does not establish causality and must not be used to retune the frozen V001 model or product thresholds.


## 19. RGB V001 target-support audit

The external Dyson failure must be separated into in-support and out-of-support cases relative to the frozen Dryad training target range.

Command:

```bash
python -m ml.weight_baseline.dyson_rgb_support_audit_v1
```

The audit uses the immutable Dryad train split only to define the observed target support:

```text
[min(train weight), max(train weight)]
```

Dyson berries are then classified as:

```text
below Dryad train support
inside Dryad train support
above Dryad train support
```

For each region it reports count, MAE, RMSE, bias, R², and max absolute error.

This is diagnostic only. It does not establish that out-of-support weight is the sole cause of model failure, and it must not be used to tune RGB V001.
