# EXP-RIP-007 — EfficientNet-B0 Backbone Screening Plan

Status: **PLANNED / LITERATURE-GROUNDED / VALIDATION ONLY**

## Change Category

`ARCHITECTURE`

## Current Evidence

The current confirmed recipe is ImageNet-pretrained ResNet-18 with full fine-tuning, AdamW, constant LR `5e-5`, weighted CrossEntropy, and validation Macro F1 checkpoint selection.

Optimization micro-variants and two loss regularization variants have already been tested. The next information-rich axis is representation capacity / backbone design rather than further coefficient tuning.

## Literature Basis

### ResNet baseline

He et al., *Deep Residual Learning for Image Recognition*, CVPR 2016.

Residual connections enable deep convolutional networks to optimize residual functions and provide the architectural basis for the current ResNet-18 baseline.

Official paper: https://openaccess.thecvf.com/content_cvpr_2016/html/He_Deep_Residual_Learning_CVPR_2016_paper.html

### EfficientNet candidate

Tan & Le, *EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks*, ICML 2019.

EfficientNet jointly scales network depth, width, and input resolution using compound scaling and reports strong accuracy/efficiency and transfer-learning behavior. EfficientNet-B0 is the smallest baseline of the family and is appropriate for a first architecture screening on a local 8GB RTX 4060 before moving to heavier models.

Official paper: https://proceedings.mlr.press/v97/tan19a.html

### Why not jump directly to ConvNeXt

Liu et al., *A ConvNet for the 2020s*, CVPR 2022, modernizes a ResNet-style ConvNet and reports strong downstream vision performance. It remains a valid later candidate, but EfficientNet-B0 is evaluated first because it provides a substantially different efficiency-oriented CNN design with modest resource cost.

Official paper: https://openaccess.thecvf.com/content/CVPR2022/html/Liu_A_ConvNet_for_the_2020s_CVPR_2022_paper.html

## Hypothesis

EfficientNet-B0 may provide a better accuracy/resource trade-off and improve maturity-boundary representation relative to ResNet-18 under the same frozen dataset and training recipe.

## Controlled Comparison

```text
Baseline
ImageNet ResNet-18
full fine-tuning
AdamW
constant LR 5e-5
weighted CrossEntropy
224x224

Candidate
ImageNet EfficientNet-B0
full fine-tuning
AdamW
constant LR 5e-5
weighted CrossEntropy
224x224
```

The architecture is the intended controlled change. Snapshot, split, augmentation, optimizer family, LR, loss, batch size, seed, early stopping, and validation selection metric remain fixed.

## Metrics

- Macro F1 — primary
- Accuracy
- per-class Precision / Recall / F1
- Ordinal MAE
- Weighted Kappa
- Confusion Matrix
- best epoch
- epoch time
- parameter count
- peak CUDA allocated memory

## Decision Rule

Single-seed screening first.

- If EfficientNet-B0 clearly regresses across primary and ordinal metrics: `REJECT` without architecture-specific micro-tuning.
- If it produces a small apparent gain: `RETEST` with paired multi-seed confirmation.
- If it produces a large coherent gain across Macro F1, ordinal metrics, and failure pattern: `PROMOTE_CANDIDATE`, still requiring confirmation before replacing the canonical model.

The frozen test set remains closed during this experiment.

## Research Policy Going Forward

Every new model-improvement experiment must distinguish:

1. **Dataset evidence** — what the current logs/confusion matrix indicate.
2. **Literature basis** — peer-reviewed/original research supporting why the proposed mechanism is plausible.
3. **Controlled hypothesis** — exactly one primary mechanism to test.
4. **Executed evidence** — actual Nongtori GPU result.

A method is not adopted merely because a paper reports good results on another dataset; Nongtori validation evidence remains the acceptance criterion.
