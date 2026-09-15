# Field Data Readiness Audit — 2026-09-15

Status: **SOURCE AUDIT / NOT TRAINING SNAPSHOT**

## Audited sources

- Google Sheet: `딸기_프로젝트`
- tabs inspected: `컬럼정보`, `농가_딸기데이터`, `농가_베드길이`
- Drive grouping folders confirmed: `남자친구농가(M)`, `응애피해농가(C)`, `외부플랫폼(U)`

## Confirmed field schema

`농가_딸기데이터` includes:

`Date, Time_Stamp, ID, Group_ID, Original_No, Weather, Farm, Zone, Variety, Class, DataType, View_Type, Occlusion, Length, Width, Weight_g, Maturity, Grade, Amb_Temp, Ref_Temp, Leaf_Temp, Amb_Humi, Light_Level, Health, Risk_Status, Final_Name`.

The source guide currently describes Maturity as `0~4 (Green, White, Turning, Mature, Full)`. This remains a working source-entry guide, not a frozen visual annotation standard for final model acceptance.

## Current stable row boundary

Rows with IDs `0001` through `0110` form the currently observed contiguous identified block.

Observed composition at the tail of this block:

- `0099`~`0110` are LEF rows;
- rows after `0110` are visibly WIP and begin losing identity fields such as `ID`, `Group_ID`, and `Original_No`.

Therefore the current ingestion gate must **not** use `Final_Name != null` as the active-row criterion. Formula-generated filenames continue to appear on incomplete WIP rows.

## Important source-quality findings

### 1. WIP rows after current contiguous ID block

Observed rows contain combinations of:

- missing ID
- missing Group_ID
- missing Original_No
- missing Farm / Class / DataType / View_Type
- missing Health / Risk fields
- generated Final_Name despite incomplete identity

Decision: classify as `PARTIAL`, preserve source, exclude from immutable training snapshot until completed.

### 2. Original_No cannot be a standalone unique key

The same `Original_No` can occur in different row contexts. Example observed in LEF rows: `P1_260106_102747_887` appears in more than one row/context.

Decision: never use Original_No alone as canonical identity. Matching must include row/domain context and, once media is available, content hash.

### 3. Date / filename timestamp inconsistency exists

Rows were observed where source `Date` is `2026.01.05` while the embedded Original_No timestamp begins `20260106`.

Decision: do not auto-correct source. Emit provenance warning `DATE_ORIGINAL_NO_TIMESTAMP_MISMATCH` and require later review.

### 4. Group_ID is a leakage boundary

The same fruit is represented by multiple views such as `RT45` and `F` under one Group_ID.

Decision: all rows sharing Group_ID must remain in the same split group. Cross-split placement is prohibited.

### 5. STR and LEF need different readiness rules

STR requires Maturity for ripeness tasks. LEF does not.

Decision: class-aware readiness validation; no global not-null rule.

## Media verification status

The three grouping folders are visible through the connected Drive source, but this session did not receive enumerable child media from those folder listings.

Therefore these claims are **not currently allowed**:

- exact physical field image count
- exact video count
- field asset SHA-256 coverage
- source-row↔physical-file completeness
- `TRAINING_READY` field snapshot

No counts are fabricated.

## Readiness gate adopted

```text
READY_METADATA
  = required task metadata present + enum/range validation passed

PARTIAL
  = source row is still being organized / required metadata missing

INVALID_FOR_TRAINING
  = explicit rule violation (invalid enum/range, stored Farm=C, etc.)

TRAINING_READY
  = READY_METADATA
    + physical asset exists
    + source match verified
    + SHA-256
    + duplicate/group policy
    + frozen label policy
    + leakage-safe split
    + immutable snapshot inclusion
```

## Next data work

1. Continue photo/video organization without modifying original source policy.
2. Run metadata readiness audit independently from physical-media audit.
3. Freeze final Maturity 0~4 visual annotation guide only after representative field examples are organized.
4. Define flower/fruit-set/non-fruit treatment.
5. Define video frame extraction/grouping/dedup policy.
6. Materialize/verify media and calculate hashes when accessible.
7. Build successor immutable snapshot only after the above gates pass.

No V009 model training is authorized before that successor snapshot exists.
