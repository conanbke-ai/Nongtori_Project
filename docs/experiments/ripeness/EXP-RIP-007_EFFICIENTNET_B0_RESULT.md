# EXP-RIP-007 — EfficientNet-B0 Architecture Screening Result

Status: **POSITIVE SCREENING / MULTI-SEED CONFIRMATION REQUIRED / VALIDATION ONLY**

## Executed evidence

- Run ID: `adc9e50ee7f0`
- Snapshot: `KGCV-RIPENESS-V001`
- Seed: `20260910`
- GPU: NVIDIA GeForce RTX 4060
- PyTorch: `2.5.1+cu121`
- CUDA: `12.1`
- Shared immutable cache: **REUSED**
- Test set evaluated: **NO**
- Successful runtime: about `07:25`

## Controlled comparison

Baseline and candidate used the same frozen snapshot, split, augmentation, input size, weighted CrossEntropy, AdamW, constant LR `5e-5`, full fine-tuning, batch size, seed, and validation-based checkpoint selection.

The controlled change was the pretrained architecture:

- baseline: ImageNet-pretrained ResNet-18
- candidate: ImageNet-pretrained EfficientNet-B0

## Selected-checkpoint result

| Metric | ResNet-18 | EfficientNet-B0 | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.9683 | **0.9741** | **+0.0058** |
| Accuracy | 0.9691 | **0.9753** | **+0.0062** |
| Ordinal MAE ↓ | 0.0432 | **0.0309** | **-0.0123** |
| Weighted Kappa | 0.9692 | **0.9781** | **+0.0089** |
| Best epoch | 2 | 7 | +5 |

EfficientNet-B0 improved the primary metric and every reported supporting ordinal metric at the Macro-F1-selected checkpoint.

## Important secondary observation

At epoch 12, EfficientNet-B0 reached:

- Macro F1: `0.9698`
- Accuracy: `0.9712`
- Ordinal MAE: `0.0288`
- Weighted Kappa: `0.9796`
- Validation loss: `0.0880`

This checkpoint had better Ordinal MAE and Kappa than the Macro-F1-selected epoch 7 checkpoint, but lower Macro F1. The existing selection policy therefore correctly retained epoch 7. This is useful evidence that checkpoint selection must remain explicit rather than cherry-picking a secondary metric after training.

## Interpretation

Unlike V003–V006, the architecture change produced a materially stronger single-seed screening signal:

- Macro F1 increased by about `0.58 percentage points`;
- accuracy increased by about `0.62 percentage points`;
- Ordinal MAE fell by about `28%` relative to the paired baseline (`0.0432 → 0.0309`);
- Weighted Kappa increased by `0.0089`.

The candidate also reached its best Macro F1 later (`epoch 7` vs `epoch 2`), indicating a meaningfully different optimization/representation trajectory rather than an identical early optimum.

However, prior experiments established that local CUDA training is not bitwise deterministic and small validation differences can reverse across seeds. Therefore this result is **not yet sufficient to replace the canonical ResNet-18 recipe**.

## Decision

`PROMOTE EFFICIENTNET-B0 TO PAIRED MULTI-SEED CONFIRMATION`

Do not perform EfficientNet-specific LR, scheduler, augmentation, or loss tuning before confirmation. First test whether the architecture advantage reproduces under multiple paired seeds.

### Confirmation gate

Promote EfficientNet-B0 to the canonical candidate only if multi-seed evidence shows a reproducible aggregate advantage, with particular attention to:

- mean Macro F1;
- per-class/M1 behavior;
- Ordinal MAE;
- Weighted Kappa;
- variance across seeds;
- parameter count / epoch runtime / peak VRAM trade-off.

If the advantage disappears, retain ResNet-18 and record V007 as a non-reproduced positive screening.

## Literature basis

Architecture selection was motivated by the original EfficientNet work (Tan & Le, ICML 2019), which proposed compound scaling of network depth, width, and resolution and reported strong accuracy/efficiency and transfer-learning behavior. The paper is used as hypothesis/design basis only; this Nongtori run is the project-specific evidence.

## Portfolio significance

V007 marks a deliberate transition from repeated optimizer/loss micro-tuning to a representation-capacity comparison after V003–V006 failed to improve the confirmed recipe. The result demonstrates the workflow:

`observed plateau → literature-grounded architecture hypothesis → controlled same-data comparison → positive screening → confirmation gate`.
