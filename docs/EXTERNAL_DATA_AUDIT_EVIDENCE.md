# External Data Audit Evidence

Status: **METADATA_AUDITED / EVIDENCE_LOCKED / RAW_IMAGE_AUDIT_PENDING**

## DATA-RIP-001 Strawberry-DS

Canonical provenance is the original Strawberry-DS Mendeley v1 / author publication.

Evidence-locked expectation:
- label/image pairs: 247
- bounding boxes: 1,062
- Green: 455
- White: 257
- Early-Turning: 28
- Turning: 35
- Late-Turning: 54
- Red: 233

The Project-AgML/Hugging Face derivative has been observed to report 1,083 boxes. It must therefore be treated as a derivative/reformatted source and must not silently replace the original Mendeley provenance. Raw audit results that do not match the canonical expectation are `MISMATCH / REVIEW_REQUIRED` until the difference is explained.

## DATA-RIP-002 KGCV Strawberry / strawberry_growth_detection

Evidence-locked facts:
- canonical origin: Zenodo 10957909 / KGCV Strawberry
- Hugging Face derivative: `Project-AgML/strawberry_growth_detection`
- pinned revision: `70f6277a609fb80fa18b431dccd04b9f09c876e0`
- rows/images: **1,477**
- bounding boxes: **3,997**
- official main-stage order: `flower`, `small g`, `green`, `white`, `turning red`, `red`, `overripe`
- tagged label format: `main_stage, diameter, length, decimal_stage`
- `decimal_stage` is within-main-stage fractional progress and must not be interpreted as a global Nongtori maturity score.

### 2026-09-10 full metadata audit

Hugging Face Dataset Viewer metadata was paged over all 1,477 rows without downloading image shards.

Actual class counts:
- flower: 539
- small g: 673
- green: 898
- white: 731
- turning red: 296
- red: 669
- overripe: 191

Total: **3,997**, errors: **0**.

Source row counts:
- random: 840
- tagged: 637

Usable `turning red` decimal-stage values exist for only **48 / 296** turning-red annotations. Distribution:

```text
0.1=15, 0.2=5, 0.3=4, 0.4=0, 0.5=10,
0.6=1, 0.7=3, 0.8=5, 0.9=5
```

Median is 0.4 and mean is approximately 0.4146. A 0.4 or 0.5 diagnostic cut happens to split the 48 decimal-tagged samples 24/24, but this is **not sufficient evidence for a Nongtori Maturity 2/3 policy threshold** because most turning-red annotations have no decimal-stage value and there is no direct field calibration link yet.

Therefore:
- `turning red -> Maturity 2/3` threshold remains **FIELD_CALIBRATION_REQUIRED**.
- no 0.5 or other threshold is promoted merely from distribution balance.
- raw `main_stage` and `decimal_stage` are preserved for later calibration.
- `overripe -> Maturity 4 + Grade JM` remains unchanged.

Detailed aggregate evidence: `docs/KGCV_LIVE_METADATA_AUDIT_20260910.md`.
Executable audit: `ml/data_pipeline/hf_metadata_audit.py`.

## Field data availability

The connected Drive exposes the `딸기_프로젝트` Sheet and farm/source grouping structure under `촬영`, but no actual image files were enumerable at the last connected-source audit. Therefore an actual field Training Snapshot containing image content hashes cannot yet be generated from the connected source.

## Automation Gate

`ml/data_pipeline/audit_expectations.py` compares audit output against evidence-locked expectations.

- exact match -> `MATCH`
- any required count mismatch -> `MISMATCH`
- missing expectation -> `NO_EXPECTATIONS`

This prevents a reformatted derivative from being silently accepted as the canonical source.
