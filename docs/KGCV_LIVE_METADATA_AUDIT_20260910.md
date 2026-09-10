# KGCV Live Metadata Audit — 2026-09-10

Status: **AUDITED / METADATA_ONLY / TURNING_RED_CALIBRATION_PENDING**

Source: `DATA-RIP-002` / `Project-AgML/strawberry_growth_detection`

Audit transport: Hugging Face Dataset Viewer metadata API. Multi-GB image archive was not downloaded. This report records aggregate annotation evidence only.

## Actual full metadata audit

- rows: **1,477 / 1,477**
- annotations: **3,997**
- audit errors: **0**
- source rows: `random=840`, `tagged=637`

### Class counts

| Stage | Count |
|---|---:|
| flower | 539 |
| small g | 673 |
| green | 898 |
| white | 731 |
| turning red | 296 |
| red | 669 |
| overripe | 191 |

The observed total is exactly 3,997 annotations and therefore matches the canonical expectation gate.

## Decimal-stage evidence

`decimal_stage` is available only on a subset of annotations and remains an intra-main-stage progress value, not a global Nongtori Maturity value.

| Stage | Decimal samples | Min | Median | Mean | Max |
|---|---:|---:|---:|---:|---:|
| flower | 152 | 0.3 | 0.5 | 0.6013 | 0.9 |
| small g | 302 | 0.1 | 0.5 | 0.4215 | 0.9 |
| green | 226 | 0.1 | 0.5 | 0.4423 | 0.9 |
| white | 235 | 0.1 | 0.5 | 0.5330 | 0.9 |
| turning red | 48 | 0.1 | 0.4 | 0.4146 | 0.9 |
| red | 149 | 0.1 | 0.5 | 0.5111 | 0.95 |
| overripe | 32 | 0.5 | 0.5 | 0.5281 | 0.8 |

### Turning-red decimal distribution

```text
0.1 = 15
0.2 = 5
0.3 = 4
0.4 = 0
0.5 = 10
0.6 = 1
0.7 = 3
0.8 = 5
0.9 = 5
```

Only **48 / 296** turning-red annotations contain a usable decimal-stage value. Therefore a threshold must not be promoted merely because the available 48 samples split conveniently.

Diagnostic counts only:

| Candidate threshold | Maturity 2 if below | Maturity 3 if >= |
|---:|---:|---:|
| 0.4 | 24 | 24 |
| 0.5 | 24 | 24 |
| 0.6 | 34 | 14 |
| 0.7 | 35 | 13 |

These are **diagnostics, not policy**.

## Mapping decision

- `turning red` without validated calibration remains `UNMAPPED` for direct Nongtori Maturity 2/3 training.
- Do not choose `0.5` merely because it yields 24/24 in the observed decimal subset.
- Preserve original `main_stage` and `decimal_stage` in the normalized provenance manifest.
- A future calibration may promote a threshold only after it is justified against Nongtori field semantics / labeled calibration samples.
- `overripe` continues to map to `Maturity=4 + Grade=JM` under the existing label policy.

## Reproducibility

The executable metadata-only auditor is `ml/data_pipeline/hf_metadata_audit.py`. CI workflow `.github/workflows/kgcv-live-audit.yml` stores the JSON report as a workflow artifact. No field source or external raw image is modified.
