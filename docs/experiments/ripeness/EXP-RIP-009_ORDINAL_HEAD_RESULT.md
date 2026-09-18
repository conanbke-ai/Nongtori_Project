# EXP-RIP-009 — EfficientNet-B0 Rank-Consistent Ordinal Head Result

Status: **REJECTED / VALIDATION ONLY / NO MULTI-SEED CONFIRMATION**
Date: **2026-09-15**

## Scope

V009 used only the frozen downloaded development snapshot `KGCV-RIPENESS-V001`.

- field / Google Drive data used: **NO**
- test set evaluated: **NO**
- seed: `20260910`
- controlled change: EfficientNet-B0 3-way softmax head → ordered cumulative-threshold ordinal head

## Result

| Metric | EfficientNet softmax | Ordinal head | Delta |
|---|---:|---:|---:|
| Accuracy | **0.9753** | 0.9527 | -0.0226 |
| Macro F1 | **0.9741** | 0.9464 | -0.0277 |
| Ordinal MAE ↓ | **0.0309** | 0.0514 | +0.0206 |
| Weighted Kappa | **0.9781** | 0.9670 | -0.0111 |
| M0 F1 | **0.9761** | 0.9577 | -0.0184 |
| M1 F1 | **0.9502** | 0.8856 | -0.0647 |
| M4 F1 | 0.9960 | **0.9960** | ~0 |

### Baseline confusion

```text
true M0: 245   5   0
true M1:   6 105   0
true M4:   1   0 124
```

### Ordinal-head confusion

```text
true M0: 249   1   0
true M1:  21  89   1
true M4:   0   0 125
```

## Interpretation

The structural ordinal head improved the M0 false-positive side (`M0→M1: 5 → 1`) but did so by becoming too conservative about predicting the middle class.

The key failure is M1 recall:

```text
softmax M1 recall : 0.9459
ordinal M1 recall : 0.8018
```

This caused `21` M1 samples to be pushed down to M0 and one M1 sample to be pushed to M4. The result is worse on the primary metric and on both ordinal supporting metrics.

The candidate also reached its best Macro F1 at epoch 15, but the remaining gap to the softmax baseline is large (`0.9464` vs `0.9741`). Extending epochs merely because the last epoch was best would amount to post-hoc rescue tuning without evidence that the formulation is competitive. The current screening is therefore sufficient to reject this formulation.

## Decision

`REJECT CURRENT ORDERED-CUMULATIVE ORDINAL HEAD`

- do **not** run paired 3-seed confirmation;
- do **not** tune threshold cutpoints or BCE weights around this implementation;
- do **not** claim structural ordinal modeling is universally unsuitable; only this specific formulation under the frozen V009 recipe is rejected;
- retain V006 and V009 together as evidence that two different ordinalization attempts did not improve the current downloaded benchmark.

## Next experiment

Move to a single literature-grounded architecture follow-up rather than tuning the rejected ordinal head.

Candidate: **ConvNeXt-Tiny** under the same downloaded snapshot and validation-only gate.

Reason:
- V007 showed representation architecture can materially change performance;
- V009 shows changing the decision head alone is not promising under the current formulation;
- ConvNeXt-Tiny provides an independent modern convolutional representation family and was already retained as a later candidate in the tuning backlog;
- resource cost must be measured alongside validation score.

## Portfolio significance

V009 is a useful negative result because it prevents repeated attempts to improve the current M0/M1 boundary by simply injecting ordinal structure. The experiment demonstrates controlled hypothesis testing and explicit rejection rather than score-driven parameter search.
