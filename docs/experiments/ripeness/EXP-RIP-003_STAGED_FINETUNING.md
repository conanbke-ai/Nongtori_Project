# EXP-RIP-003 — Staged Fine-tuning Screening

Status: **REJECTED / MEANINGFUL GPU EVIDENCE / VALIDATION ONLY**

## Evidence

- Task: ripeness / maturity ordinal classification
- Execution: local CUDA GPU
- GPU: NVIDIA GeForce RTX 4060 8GB
- PyTorch: `2.5.1+cu121`
- CUDA runtime: `12.1`
- Snapshot: `KGCV-RIPENESS-V001`
- Seed: `20260910`
- Test evaluated: **NO**
- Change category: `OPTIMIZATION`
- Controlled change: trainable-parameter schedule only
- LR: `5e-5` for both baseline and candidate
- Model: ImageNet-pretrained ResNet-18
- Optimizer: AdamW
- Weight decay: `1e-4`
- Batch size: 32
- Train / Valid: `2243 / 486`
- Local structured run id: `35c5b0b463fd`
- Total successful run duration: about `06:16`

## Observed Problem

After EXP-RIP-002, LR `5e-5` was confirmed as a more stable full-fine-tuning recipe than `3e-4`, but train loss still fell rapidly while validation performance saturated early.

## Hypothesis

Training only the classifier head for the first two epochs, then unfreezing the full backbone, could preserve pretrained features during the earliest optimization steps and improve validation generalization.

## Controlled Comparison

### Current confirmed recipe

```text
ResNet-18
LR 5e-5
epoch 1 onward: full backbone trainable
```

### Candidate staged recipe

```text
ResNet-18
LR 5e-5
epoch 1-2: classifier head only
epoch 3 onward: full backbone trainable
```

All other relevant variables were kept fixed.

## Actual Result

### Full fine-tuning @ 5e-5

Best checkpoint:

- Best epoch: **2**
- Validation Macro F1: **0.9683**
- Accuracy: **0.9691**
- Ordinal MAE: **0.0432**
- Weighted Kappa: **0.9692**
- Validation loss: **0.0942**
- Checkpoint SHA prefix: `e039dba1f191`

The full-fine-tuning run early-stopped after epoch 7 with epoch 2 remaining the best Macro-F1 checkpoint.

### Staged fine-tuning @ 5e-5

Best Macro-F1 checkpoint:

- Best epoch: **8**
- Validation Macro F1: **0.9654**
- Accuracy: **0.9671**
- Ordinal MAE: **0.0494**
- Weighted Kappa: **0.9677**
- Validation loss: **0.0856**
- Checkpoint SHA prefix: `4f52d936b57b`

The staged run early-stopped after epoch 13.

A different staged epoch (epoch 6) reached:

- Validation loss: **0.0831**
- Macro F1: **0.9631**
- Ordinal MAE: **0.0453**
- Weighted Kappa: **0.9707**

This means staged training sometimes improved individual secondary metrics, but it did not produce a checkpoint that simultaneously surpassed the confirmed full-fine-tuning recipe on the primary selection metric.

## Delta at Selected Checkpoints

| Metric | Full 5e-5 | Staged 5e-5 | Staged Δ |
|---|---:|---:|---:|
| Macro F1 | **0.9683** | 0.9654 | **-0.0029** |
| Accuracy | **0.9691** | 0.9671 | **-0.0020** |
| Ordinal MAE ↓ | **0.0432** | 0.0494 | **+0.0062** |
| Weighted Kappa | **0.9692** | 0.9677 | **-0.0015** |
| Best Epoch | 2 | 8 | +6 |

## Interpretation

The hypothesis was not supported under the current dataset/model/LR combination.

The staged recipe did delay the best Macro-F1 epoch from 2 to 8, showing that the optimization trajectory changed as intended. However, the delayed optimum did **not** translate into better primary validation performance.

The first two head-only epochs also produced very weak validation performance (`Macro F1 0.4660 → 0.5672`) before the backbone was unfrozen. Once unfrozen, performance recovered quickly, but the final best checkpoint still did not exceed the simpler full-fine-tuning recipe.

Therefore, the added training complexity is not justified by the observed benefit.

## Decision

`REJECT STAGED FINE-TUNING FOR CURRENT RESNET-18 RECIPE`

Keep the current confirmed recipe:

```text
ResNet-18
full fine-tuning from epoch 1
LR 5e-5
```

Do not retune warm-up length repeatedly. The current experiment already provides enough evidence that a simple 2-epoch head-only warm-up is not an improvement worth pursuing.

## What This Experiment Changed

This experiment rules out one optimization branch and prevents repeated warm-up tuning without evidence.

The next improvement axis should therefore move to a different mechanism rather than revisiting LR or staged warm-up. Per the canonical strategy, the next controlled optimization candidate is a learning-rate scheduler, still using full fine-tuning at the confirmed base LR `5e-5`.

## Reliability / Scope

- actual GPU execution: YES
- frozen snapshot: YES
- same validation split: YES
- test tuning: NO
- structured logs/checkpoints: YES
- candidate outperformed primary metric: NO
- decision-changing evidence: YES
- production / field validation: NO

The earlier Windows DataLoader multiprocessing failure is intentionally excluded from model-improvement evidence because it was an execution-environment compatibility bug, not a model result.
