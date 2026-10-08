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
