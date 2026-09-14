# EXP-RIP-006 — Expected Ordinal Distance Regularization

Status: **REJECTED / LOCAL GPU SCREENING / VALIDATION ONLY**

## Evidence

- Task: ripeness / maturity ordinal classification
- Change Category: `LOSS`
- Execution: local CUDA GPU
- GPU: NVIDIA GeForce RTX 4060 8GB
- PyTorch: `2.5.1+cu121`
- CUDA runtime: `12.1`
- Snapshot: `KGCV-RIPENESS-V001`
- Seed: `20260910`
- Structured run id: `a62b466f71e3`
- Test evaluated: **NO**
- Shared cache: **REUSED**
- Model: ImageNet-pretrained ResNet-18
- Fine tuning: full backbone from epoch 1
- Optimizer: AdamW
- LR: constant `5e-5`
- Baseline loss: weighted CrossEntropy
- Candidate loss: weighted CrossEntropy + `0.20 × expected normalized maturity distance`
- Maturity values used for distance: `[0, 1, 4]`
- Successful run duration: about `04:19`

## Hypothesis

Because maturity classes are ordered, a loss that penalizes probability mass farther from the true maturity more strongly could improve ordinal behavior beyond standard CrossEntropy.

## Controlled Change

Only the loss changed.

```text
Baseline
weighted CrossEntropy

Candidate
weighted CrossEntropy
+ 0.20 × expected normalized maturity distance
```

Model, pretrained initialization, data, split, augmentation, optimizer, LR, batch size, seed, and checkpoint selection were unchanged.

## Actual Result

| Metric | Baseline | Ordinal-aware loss | Delta |
|---|---:|---:|---:|
| Macro F1 | **0.9703** | 0.9683 | **-0.0020** |
| Accuracy | **0.9712** | 0.9691 | **-0.0021** |
| Ordinal MAE ↓ | **0.0412** | 0.0432 | **+0.0020** |
| Weighted Kappa | **0.9707** | 0.9692 | **-0.0015** |
| Best epoch | 2 | 2 | 0 |

The candidate did not improve the ordinal metrics it was specifically designed to target.

## Interpretation

The expected-distance term altered the objective but did not improve decision quality on the frozen validation split. The degradation was small but consistent across all reported primary/ordinal metrics.

Because the candidate lost on both Macro F1 and the ordinal-sensitive metrics, there is no evidence to justify a lambda micro-sweep around `0.20`.

## Reproducibility Note

The same nominal seed has produced small baseline variation across local GPU runs (`0.9683` vs `0.9703` Macro F1 in different experiments). Current code permits nondeterministic CUDA kernels (`torch.use_deterministic_algorithms(False)`), so exact bitwise reproducibility is not guaranteed.

For this experiment the baseline and candidate were executed within the same run under the same environment and frozen snapshot, so the paired direction is still valid for screening. Future acceptance work should explicitly distinguish:

- stochastic single-run screening;
- paired multi-seed confirmation;
- exact deterministic reproducibility.

## Decision

`REJECT EXPECTED-ORDINAL-DISTANCE REGULARIZATION (λ=0.20)`

Keep the current confirmed loss:

```text
weighted CrossEntropy
label_smoothing = 0
```

Do not micro-sweep nearby ordinal lambda values based on this result.

## Next Action

The next experiment should move away from simple additive loss regularization. A backbone/architecture comparison is now more justified than continuing to tweak small loss coefficients, unless a genuinely different ordinal formulation is introduced with a clear structural hypothesis.

## Reliability / Scope

- actual local GPU execution: YES
- frozen snapshot: YES
- shared cache reuse: YES
- controlled variable isolation: YES
- test tuning: NO
- multi-seed confirmation: NOT REQUIRED AFTER CLEAR SCREENING LOSS
- field validation: NO
