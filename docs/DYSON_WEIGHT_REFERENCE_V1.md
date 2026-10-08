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
