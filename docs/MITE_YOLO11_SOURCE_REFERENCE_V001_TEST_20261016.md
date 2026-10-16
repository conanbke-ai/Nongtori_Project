# Mite YOLO11 Source-Reference V001 Public Test Result — 2026-10-16

Status: **SOURCE_REFERENCE_TEST_FROZEN / MORPHOLOGY_RESEARCH_COMPLETE**

## Checkpoint

SHA-256:

`eb962a8d879674c9d0fa1cc08ba707ca1f2dc1b094e0e9350baf9e2f2c231529`

Role:

`SOURCE_REFERENCE_PORTFOLIO_ONLY`

Selection from this test is prohibited.

## Public test cohort

- images: 192
- instances: 2,722
- snapshot: MITE-PUBLIC-MORPHOLOGY-V001
- split policy: Nongtori leakage-safe connected origin/hash grouping

## Aggregate test result

| Metric | Result |
|---|---:|
| Precision | 0.908224 |
| Recall | 0.859457 |
| mAP50 | 0.925419 |
| mAP50-95 | 0.568616 |

## Per-class result

| Class | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|
| Adult_female | 0.835 | 0.887 | 0.911 | 0.517 |
| Immature | 0.944 | 0.765 | 0.893 | 0.483 |
| Viable_egg | 0.945 | 0.926 | 0.972 | 0.705 |

## Validation-to-test change

Validation:
- mAP50: 0.932762
- mAP50-95: 0.581520

Test:
- mAP50: 0.925419
- mAP50-95: 0.568616

Delta:
- mAP50: -0.007343
- mAP50-95: -0.012903

The drop is modest and does not indicate collapse.

## Comparison with official miteVision v210

Official reported v210 test reference:
- Precision ~0.875
- Recall ~0.871
- mAP50 ~0.883
- mAP50-95 ~0.601

Nongtori leakage-safe test:
- Precision 0.908
- Recall 0.859
- mAP50 0.925
- mAP50-95 0.569

This is not an equivalence reproduction claim. Differences include:
- Nongtori leakage-safe reassigned split;
- RTX 4060 batch 2 vs source A100 40GB batch 16;
- source v210 synthetic-data usage not reproduced;
- different runtime/library environment.

## Product interpretation

This experiment completes the intended source-reference / portfolio objective.

The three life-stage classes are not promoted as Nongtori product-facing outputs.

For Portfolio V1:
- RGB mite detection remains auxiliary corroboration evidence;
- absence of RGB detection must not be treated as MITE_NEGATIVE;
- pest-risk modeling returns to Thermal-first inputs and environment context;
- no further YOLO morphology architecture search is planned.

Field readiness remains NOT_ESTABLISHED.
