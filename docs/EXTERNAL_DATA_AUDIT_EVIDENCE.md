# External Data Audit Evidence

Status: **PARTIAL_RAW_AUDIT / EVIDENCE_LOCKED**

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
- rows/images: 1,477
- bounding boxes: 3,997
- official main-stage order: `flower`, `small g`, `green`, `white`, `turning red`, `red`, `overripe`
- tagged label format: `main_stage, diameter, length, decimal_stage`
- `decimal_stage` is within-main-stage fractional progress in the official implementation and must not be interpreted as a global Nongtori maturity score.

Raw per-class counts and the actual `turning red` decimal-stage distribution are not yet evidence-locked because the full raw annotation archive was not available in this execution environment.

Therefore:
- `turning red -> Maturity 2/3` threshold remains **UNRESOLVED**.
- no 0.5 or other threshold may be invented.
- running `audit-kgcv` against the extracted raw annotation directory is the required gate before calibration.

## Field data availability

The connected Drive exposes the `딸기_프로젝트` Sheet and farm-scoped folder structure under `촬영`, but no actual image files were enumerable in the connected Drive search at this time. Therefore an actual field Training Snapshot containing image content hashes cannot yet be generated from the connected source.

## Automation Gate

`ml/data_pipeline/audit_expectations.py` compares raw audit output against evidence-locked expectations.

- exact match -> `MATCH`
- any required count mismatch -> `MISMATCH`
- missing expectation -> `NO_EXPECTATIONS`

This prevents a reformatted derivative from being silently accepted as the canonical source.
