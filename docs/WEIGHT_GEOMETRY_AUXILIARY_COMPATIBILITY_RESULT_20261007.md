# WEIGHT Geometry Auxiliary Compatibility Result — 2026-10-07

Status: **REJECTED_FOR_PORTFOLIO_V1_AUGMENTATION**

## Summary

The 1,047 auxiliary Dryad geometry+weight fruit are not adopted into Nongtori Weight V1 training.

Reason:

- source values are intact;
- the problem is not label corruption;
- the auxiliary cohort differs materially from the strict RGB-weight cohort in composition and acquisition context;
- naive concatenation already degraded train-only OOF metrics;
- reweighting by grade distribution alone is not sufficient evidence that the cohorts are exchangeable.

## Source integrity

The compatibility audit re-read canonical Dryad metadata and verified all 1,047 auxiliary rows against source values.

Verified unchanged fields:

- weight_with_calyx_g
- width_mm
- height_mm
- variety
- source_sheet
- photo

No source target or geometry value was modified.

## Cohort composition

Strict official train:

- 367 fruit
- photo=YES for all 367
- mean weight 18.7487g
- mean width 34.2670mm
- mean height 35.7847mm

Auxiliary:

- 1,047 fruit
- photo=NO 1,039 / YES 8
- mean weight 21.1139g
- mean width 35.6514mm
- mean height 37.8615mm

Distribution shift:

- grade TV distance: 0.1542
- variety TV distance: 0.7469
- source-sheet TV distance: 0.9456
- photo TV distance: 0.9924

These differences are too large to treat the auxiliary cohort as a simple random extension of the strict photo-backed cohort.

## Geometry relation transfer

Strict train 5-fold OOF:

- MAE 1.3698g
- RMSE 1.9282g
- R² 0.9185
- grade errors 59
- threshold crossings 60

Auxiliary-trained model evaluated on strict train:

- MAE 1.4215g
- RMSE 1.9580g
- R² 0.9160
- grade errors 62
- threshold crossings 63

Strict-trained model evaluated on auxiliary:

- MAE 1.5236g
- RMSE 2.0548g
- R² 0.8964
- grade errors 191 / 1,047
- threshold crossings 191

The geometry→weight relation transfers only partially across cohorts.

## Shared-variety evidence

The mismatch remains inside shared varieties.

Examples:

- 1975: strict mean 24.16g vs auxiliary 20.62g
- 269: strict mean 17.95g vs auxiliary 12.00g
- Monterey: strict mean 19.17g vs auxiliary 25.53g
- San Andreas: strict mean 12.54g vs auxiliary 20.95g

Therefore a grade-distribution balancing rule alone cannot explain or repair the difference.

## Decision

For Nongtori Portfolio V1:

```text
Geometry V2 naive auxiliary concatenation
→ REJECTED

Geometry V3 grade-matched reweighting
→ NOT RUN / REJECTED FOR V1

Canonical Geometry benchmark
→ retain strict-cohort Geometry V001
```

The auxiliary cohort remains preserved as research/reference data.

Future use requires a separately scoped source-aware or variety-aware study, not an automatic weighting rule.

## Next Weight V1 direction

Do not spend further V1 time on auxiliary Geometry training.

Next priority:

1. retain Fusion V001 as current weight benchmark;
2. investigate RGB multi-view information use;
3. evaluate model disagreement only with leakage-safe development evidence;
4. then freeze Weight ML V1 and complete runtime/UI/QA integration.

