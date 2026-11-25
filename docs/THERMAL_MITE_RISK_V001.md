# Thermal-first Mite Risk V1 — Source Alignment and Feature Contract

Date: 2026-10-16

Status: **SOURCE-ALIGNED DESIGN / CALIBRATION PENDING**

## Product objective

Nongtori does not treat RGB mite detection as the primary pest model.

Canonical V1 direction:

```text
Thermal + Environment + History
→ risk / novelty / trend / spatial signals
→ scouting CASE

RGB mite detector
→ auxiliary corroboration evidence only
```

Absence of RGB detection is never converted into `MITE_NEGATIVE`.

## Source evidence

### PAPER-PEST-001

Thermal-response mechanism reference:
- da Cunha Lima et al., Agronomy 2025, 15(10), 2297
- Tetranychus mexicanus on passion fruit
- thermography showed a measurable difference between infested and control plants
- the infested plants were slightly cooler in that experiment
- authors discuss thermal response as context-dependent through host physiology,
  stomatal behavior and transpiration

Implication for Nongtori:
- do not encode `warmer leaf = higher mite risk`;
- do not encode `cooler leaf = higher mite risk`;
- model relative thermal context and let field evidence determine direction.

### PAPER-PEST-002

Strawberry / T. urticae physiological early-detection reference:
- time-series hyperspectral study on strawberry
- same crop and mite species as Nongtori target
- demonstrates measurable physiological change and value of repeated sensing

Implication:
- supports temporal/contextual physiological risk modeling;
- hyperspectral thresholds are not transferred into thermal features.

## Current field columns

Existing Nongtori sheet already includes:
- Amb_Temp
- Ref_Temp
- Leaf_Temp
- Amb_Humi
- Light_Level
- Health
- Risk_Status

These inputs are sufficient to build a non-destructive feature layer before the
final field-label policy and image organization are complete.

## V1 deterministic features

Required:
- leaf temperature
- ambient temperature
- ambient RH

Derived:
- leaf minus ambient temperature
- leaf minus reference temperature
- ambient VPD
- leaf VPD using ambient vapor pressure
- leaf-air VPD delta
- absolute thermal deviation from reference

Optional:
- light level
- RGB mite evidence confidence
- timestamp/history/spatial context at the later aggregation layer

No fixed anomaly threshold is embedded in this feature layer.

## Training gate

Model fitting is deliberately blocked until both are true:

1. field label policy is frozen;
2. field cohort/split audit is complete.

Initial candidate models after the gate:
- logistic regression as interpretable baseline;
- XGBoost as nonlinear tabular candidate.

Large sequence models are not V1 requirements because current repeated observations
are irregular and field data volume is limited.

## Evaluation

When labels are ready:
- farm/spatial-group holdout where feasible;
- AUROC and AUPRC;
- sensitivity/specificity;
- calibration error;
- operational alert precision and alert burden;
- no test-based tuning.

## Product boundary

Thermal signal is a risk indicator, not a species-specific diagnosis.

Field confirmation, RGB corroboration and repeated observations can increase confidence,
but no single missing evidence stream is silently interpreted as a negative label.

---

## 2026-11-24 Thermal-first / low-data adaptation clarification

**Policy status: ADOPTED / NO NEW MODEL TRAINING.** Mite early warning is based on leaf thermal physiology (relative leaf/reference/ambient temperature, VPD, time and spatial pattern), environmental covariates and independently verified outcomes. High-resolution RGB mite/egg detection or ZERO/VFM zero-shot/few-shot detection is **auxiliary corroboration/research**, not the primary early-warning objective.

- Require provenance for radiometric thermal values vs palette-rendered screenshots; never interpret pixel colors as absolute °C without validated calibration and palette metadata. Preserve device calibration, units, capture time, source hash and reference region when available.
- Candidate observational labels: `CONFIRMED_POSITIVE`, `CONFIRMED_NEGATIVE`, `UNVERIFIED`, `UNKNOWN`; confirmed negative requires actual documented inspection protocol, not missing RGB detections. Do not infer mites from `Health` or `Risk_Status` alone.
- Pair temporal, plant/leaf, farm/zone and environmental observations. Capture matched positive, inspected-negative, other-stress confounder and repeated observations; no fixed warmer/cooler direction or risk threshold without field calibration. Observed mite after symptoms and true lead-time early warning must be reported separately.
- For very small datasets, first test interpretable Logistic Regression and XGBoost on verified features; low-data/few-shot domain adaptation is a *conditional* study, not an automatic VFM replacement. A 10/20/50-case support cohort is illustrative only; sampling unit, independent validation/test and uncertainty must be specified. Do not label repeated frames from one leaf as independent shots.
- Evaluate sensitivity/false alarms per farm/zone, AUPRC/AUROC, calibration, lead time, domain holdout, robustness to illumination/water-stress/confounders and missing inputs. A generic abnormal thermal signal is not a species-specific positive diagnosis.
- Preserve source-aligned paper-based baseline architecture and predeclared epoch/patience settings for existing RGB reference experiments. No arbitrary replacement with tutorial values; later tuning requires hypothesis, fixed split and separate evidence. Thermal tabular baseline does not inherit YOLO epoch/patience.
- No model fitting until canonical field label policy and cohort/split gate are complete. Product inference remains disabled until validated and deployed under existing authorization/worker QA policies.
