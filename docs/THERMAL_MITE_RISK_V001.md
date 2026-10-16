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
