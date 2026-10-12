# Dyson External RGB V001 Result Freeze — 2026-10-12

Status: **EXTERNAL_GENERALIZATION_FAILED / DOMAIN_SHIFT_CONFIRMED**

## 1. Scope

This result freezes the non-commercial external evaluation of Nongtori Weight RGB V001 on the ICRA/Dyson strawberry reference dataset.

The Dyson dataset remains:

```text
dataset_role = NON_COMMERCIAL_REFERENCE
commercial_training_ready = false
benchmark_role = EXTERNAL_NON_COMMERCIAL_REFERENCE
```

No Dyson sample was used for retraining, fine-tuning, threshold selection, aggregation selection, or model selection.

## 2. Frozen benchmark inputs

Dryad source model:

```text
model = EFFICIENTNET_B0_IMAGENET
checkpoint = artifacts/weight/rgb-v001/best.pt
training dataset = WEIGHT-DRYAD-V001
training policy = frozen RGB V001
```

Dyson external pipeline:

```text
637 strict physical berries
→ 1,900 expected berry-view observations
→ 1,868 UNIQUE_GEOMETRIC_MATCH rows
→ 1,868 materialized berry crops
→ 631 physical berries with at least one evaluable crop
```

Crop materialization result:

```text
eligible_unique_join_count = 1868
materialized_count = 1868
successful_crop_count = 1868
source_rgb_missing_count = 0
bbox_out_of_bounds_count = 0
excluded_non_unique_join_count = 32
```

## 3. External RGB V001 result

Dyson external result:

```text
n_berries = 631
n_views = 1868

MAE = 7.6294 g
RMSE = 10.2286 g
R² = -1.0840
Bias = -5.9412 g
MaxAE = 84.9534 g

Grade accuracy = 27.10%
Grade errors = 460
```

Reference Dryad internal test result for RGB V001:

```text
MAE = 1.2401 g
RMSE = 2.3446 g
R² = 0.8852
Bias = -0.4192 g
Grade accuracy = 83.33%
```

Decision:

```text
DYSON_EXTERNAL_RGB_GENERALIZATION_FAILED
```

The Dryad-trained RGB V001 model must not be presented as dataset-independent or field-general weight estimation.

## 4. Target-distribution audit

Dryad test:

```text
count = 78
mean = 17.7081 g
median = 15.8 g
std = 6.9205 g
min = 7.01 g
max = 51.07 g
```

Dyson:

```text
count = 631
mean = 16.9794 g
median = 17.0 g
std = 7.0854 g
min = 1.7 g
max = 104.0 g
```

Shift summary:

```text
mean delta = -0.7287 g
median delta = +1.2 g
std delta = +0.1649 g
grade total variation = 0.1601
```

Interpretation:

The overall target mean and standard deviation are similar enough that simple target-distribution shift alone does not explain the generalization collapse.

## 5. Dryad-train support audit

Dryad train target support:

```text
count = 367
min = 6.23 g
max = 44.08 g
```

Dyson overlap:

```text
below train support = 25 / 631 (3.96%)
inside train support = 605 / 631 (95.88%)
above train support = 1 / 631 (0.16%)
```

Performance inside the Dryad train target support:

```text
count = 605
MAE = 7.5911 g
RMSE = 9.4379 g
R² = -1.7617
Bias = -6.2007 g
MaxAE = 30.0647 g
```

Decision:

```text
TARGET_SUPPORT_MISMATCH_NOT_SUFFICIENT_TO_EXPLAIN_FAILURE
```

The external failure persists even for berries whose actual weight is within the Dryad train target range.

## 6. Input-domain audit

Comparison:

```text
Dryad frozen test RGB views = 1,716
Dyson materialized berry crops = 1,868
```

Both cohorts were inspected after the same geometric RGB V001 evaluation preprocessing:

```text
Resize short edge to 256
→ CenterCrop 224
→ measure pixel statistics before ImageNet normalization
```

Largest low-level standardized mean differences:

```text
source_width                  -212.16
source_height                 -105.35
source_aspect_ratio            -14.79
saturation_mean                 +3.71
b_mean                          -3.00
center_crop_retained_fraction   +2.71
luminance_std                   -2.70
r_std                           -2.57
```

Important interpretation guard:

The enormous source width/height and aspect-ratio differences mainly reflect a structural representation mismatch:

```text
Dryad = full controlled source image
Dyson = berry-level crop
```

They are not standalone causal evidence.

The more informative pixel-domain differences are:

```text
Dyson saturation mean:
0.7099 vs Dryad 0.3871

Dyson blue-channel mean:
0.1586 vs Dryad 0.3951

Dyson luminance mean:
0.2971 vs Dryad 0.4613

Dyson luminance std:
0.1142 vs Dryad 0.1953
```

These results support a substantial low-level input-domain shift in color, brightness, saturation, and contrast.

## 7. Final interpretation

Evidence chain:

```text
Dryad internal RGB V001 performs well
        ↓
Dyson external benchmark fails badly
        ↓
Most Dyson targets remain inside Dryad train target support
        ↓
Failure persists inside target support
        ↓
Low-level image statistics differ materially
        ↓
EXTERNAL INPUT DOMAIN SHIFT IS A PLAUSIBLE MAJOR CONTRIBUTOR
```

This is not a causal proof that low-level pixel shift alone explains the error.

Other differences may contribute:

- full-image vs berry-crop framing;
- camera / optics / illumination;
- background and segmentation context;
- apparent berry scale;
- dataset acquisition protocol;
- cultivar / phenotype differences;
- view-count and multi-view composition differences.

## 8. Portfolio interpretation

Portfolio-safe claim:

> Nongtori Weight RGB V001 achieved strong in-domain performance on the frozen Dryad benchmark, but external evaluation on 631 Dyson berries showed severe generalization degradation. Follow-up audits demonstrated that the failure persisted for 95.9% of Dyson berries within the Dryad training target range and identified substantial image-domain differences in saturation, brightness, channel statistics, contrast, and framing. The result was therefore retained as an explicit domain-generalization limitation rather than hidden or retuned against the external reference set.

Do not claim:

- external robustness;
- field-general weight estimation;
- commercial readiness from Dyson;
- causal attribution to one image statistic;
- improved Dyson performance through tuning.

## 9. Frozen decision

```text
RGB V001:
  DRYAD_IN_DOMAIN_BENCHMARK = ACCEPTED
  DYSON_EXTERNAL_GENERALIZATION = FAILED

Dyson:
  EXTERNAL_NON_COMMERCIAL_REFERENCE_ONLY

NEXT:
  do not tune RGB V001 on Dyson
  do not merge Dyson into commercial training
  move portfolio priority toward product/API/UI/field acceptance
  revisit external robustness only in a clearly versioned successor research track
```
