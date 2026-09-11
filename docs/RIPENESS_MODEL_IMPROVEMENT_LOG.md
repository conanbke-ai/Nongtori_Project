# Nongtori Ripeness Model Improvement Log

Status: **CANONICAL / EXECUTED EVIDENCE ONLY**

이 문서는 Nongtori 숙도 모델에서 **실제로 실행된 실험 중 의사결정에 의미 있는 결과만** 기록한다.

아직 실행하지 않은 개선 아이디어나 parameter 후보는 이 문서에 기록하지 않는다. 그런 내용은 `docs/MODEL_IMPROVEMENT_STRATEGY.md`에서 관리한다.

기록 기준은 `docs/MODEL_EXPERIMENT_EVIDENCE_POLICY.md`를 따른다.

---

# EXP-RIP-001 — ResNet-18 Baseline Reproduction

## Evidence

- Experiment: `RIPENESS-BASELINE-V001`
- Snapshot: `KGCV-RIPENESS-V001`
- Assignment SHA-256: `5e2424f7c26d84e4f8d43ca90ba60b46806eb9d7bb361669c8b42ad27f2040ea`
- Model: ImageNet-pretrained ResNet-18
- Fine tuning: full backbone trainable from epoch 1
- Optimizer: AdamW
- Learning rate: `3e-4`
- Weight decay: `1e-4`
- Batch size: 32
- Seed: `20260910`
- Train / Valid / Test: `2243 / 486 / 433`
- Best checkpoint SHA-256: `e9a746113d6d28edb481665ae23b59d9bf542dc9f9da3fb7465488cb2aea8a17`
- Run duration: 1,344.188 sec
- Errors: 0
- Status: `REPRODUCED`

## Observed Problem

숙도 분류의 재현 가능한 기준선이 없어서 이후 개선 모델을 객관적으로 비교할 수 없었다.

또한 실제 학습 결과에서 다음 두 문제가 확인되었다.

1. Maturity 1이 가장 약한 class였다.
2. validation best checkpoint가 epoch 1에서 발생했고 이후 5 epoch 동안 갱신되지 않았다.

## Controlled Setup

이 실험은 성능 개선 실험이 아니라 **기준선 확립 실험**이다.

다음 조건을 고정했다.

- frozen snapshot 사용
- exact split assignment checksum 검증
- ImageNet pretrained ResNet-18
- full fine tuning
- AdamW
- LR `3e-4`
- 동일 seed
- validation Macro F1 기준 checkpoint 선택
- test set은 configuration 선택에 사용하지 않음

## Actual Validation Result

- Best validation Macro F1: **0.9536944102**
- Best validation M1 F1: **0.9177489177**
- Best validation Ordinal MAE: **0.0679012346**
- Best validation Weighted Kappa: **0.9603116512**
- Best epoch: **1**
- Early stopping: epoch 6

학습이 계속 진행되는 동안 epoch 1의 validation Macro F1을 넘지 못했다.

이 결과는 현재 full fine-tuning recipe가 빠르게 과적합되는지 확인해야 한다는 실제 근거가 되었다.

## Actual Frozen Test Result

| Metric | Result |
|---|---:|
| Accuracy | 0.9422632794 |
| Macro F1 | 0.9402391674 |
| Ordinal MAE | 0.0900692841 |
| Weighted Kappa | 0.9419644636 |
| Test Loss | 0.1516360879 |

### Per-class

| Maturity | Precision | Recall | F1 |
|---|---:|---:|---:|
| M0 | 0.9673913043 | 0.9081632653 | 0.9368421053 |
| M1 | 0.8660714286 | 0.9417475728 | **0.9023255814** |
| M4 | 0.9708029197 | 0.9925373134 | 0.9815498155 |

### Confusion Matrix

Rows=true, columns=predicted, order `[0, 1, 4]`:

```text
[[178, 14,  4],
 [  6, 97,  0],
 [  0,  1,133]]
```

### Actual Failure Pattern

- M0 → M1: **14**
- M0 → M4: 4
- M1 → M0: 6
- M4 → M1: 1

가장 명확한 오류 패턴은 **M0/M1 경계 혼동**이다.

M1 Recall은 0.9417로 높지만 Precision이 0.8661로 낮다. 즉 실제 M1을 놓치는 것보다 M0를 M1로 과대 판정하는 문제가 더 크다.

## What This Experiment Established

1. frozen KGCV snapshot에서 ResNet-18 baseline을 재현 가능하게 학습할 수 있다.
2. 전체 성능의 주된 약점은 Maturity 1이다.
3. M0 → M1 오분류가 가장 큰 단일 confusion이다.
4. M4는 이미 F1 0.9815로 매우 강하므로 현재 최우선 병목은 M4가 아니다.
5. best epoch가 1이라는 사실 때문에 현재 optimization recipe의 과적합 가능성을 검증할 필요가 있다.
6. 이 모델은 external KGCV domain의 M0/M1/M4만 평가한 것이므로 production reliability 또는 FIELD_VALIDATED로 해석할 수 없다.

## Reliability

- 실제 실행 완료: YES
- frozen split 검증: YES
- checkpoint artifact: YES
- structured logs: YES
- final test artifact: YES
- multi-seed confirmation: NO
- field validation: NO

## Decision

`KEEP AS REPRODUCED BASELINE`

이 모델은 배포 후보로 채택한 것이 아니라 이후 모든 개선 실험의 비교 기준선으로 유지한다.

---

# EXP-RIP-002 — Lower Full-Fine-Tuning LR Screening

Status: **SCREENING / MEANINGFUL EVIDENCE / NOT YET CONFIRMED**

## Evidence

- GitHub Actions run: `34561786597`
- Structured run id: `f7a06f1bd8bd`
- Artifact: `ripeness-v002-lr-screening`
- Snapshot: `KGCV-RIPENESS-V001`
- Assignment SHA-256: `5e2424f7c26d84e4f8d43ca90ba60b46806eb9d7bb361669c8b42ad27f2040ea`
- Seed: `20260910`
- Test evaluated: **NO**
- Compared variable: learning rate only
- Fixed: model, optimizer family, weight decay, batch size, augmentation, snapshot, split, seed, class weighting, early-stopping rule

## Observed Problem

Baseline LR `3e-4`에서 validation best가 epoch 1에 발생한 뒤 개선되지 않았다.

이는 pretrained backbone을 처음부터 full fine-tuning할 때 LR이 과도해 유용한 pretrained feature를 빠르게 훼손하거나, validation optimum을 너무 일찍 지나칠 가능성을 시사했다.

## Hypothesis

**full-backbone learning rate를 낮추면 optimization이 안정화되고 M0/M1 경계 성능이 개선될 수 있다.**

이 가설만 검증하기 위해 `1e-4`, `5e-5` 두 조건만 비교했다.

## Actual Validation Result

| Metric | Baseline `3e-4` | `1e-4` | Δ vs Base | `5e-5` | Δ vs Base |
|---|---:|---:|---:|---:|---:|
| Macro F1 | 0.953694 | 0.969563 | +0.015868 | **0.971656** | **+0.017961** |
| M1 F1 | 0.917749 | 0.946903 | +0.029154 | **0.951111** | **+0.033362** |
| Ordinal MAE ↓ | 0.067901 | 0.045267 | -0.022634 | **0.043210** | **-0.024691** |
| Weighted Kappa | 0.960312 | 0.970794 | +0.010482 | **0.972190** | **+0.011879** |
| Best epoch | 1 | 3 | +2 | 2 | +1 |

상대적으로 `5e-5`는 baseline 대비:

- Macro F1: 약 **+1.88%**
- M1 F1: 약 **+3.64%**
- Ordinal MAE: 약 **36.36% 감소**
- Weighted Kappa: 약 **+1.24%**

으로 개선되었다.

## Failure Pattern Comparison

Baseline best validation confusion matrix:

```text
[[237, 12, 1],
 [  4,106, 1],
 [  1,  2,122]]
```

`5e-5` best validation confusion matrix:

```text
[[243, 7, 0],
 [  3,107, 1],
 [  2, 0,123]]
```

주요 관찰:

- M0 → M1: `12 → 7`
- M1 → M0: `4 → 3`
- M4 → M1: `2 → 0`
- M1 F1: `0.9177 → 0.9511`

즉 전체 점수만 오른 것이 아니라 **실제로 개선하려던 M0/M1 경계 오류가 감소했다.**

## Learning Behavior

- Baseline best epoch: 1
- `1e-4` best epoch: 3
- `5e-5` best epoch: 2

낮은 LR에서 validation optimum이 epoch 1 이후로 이동했다. 따라서 "기존 LR이 다소 공격적이었다"는 가설을 지지하는 방향이다.

다만 두 후보 모두 이후 train loss가 매우 낮아지는 동안 validation 개선은 지속되지 않았으므로, LR 감소만으로 일반화 문제가 완전히 해결됐다고 보지는 않는다.

## Why This Is Meaningful Evidence

이 실험을 기록하는 이유는 단순히 metric이 조금 올랐기 때문이 아니다.

1. 변경 변수는 LR 하나뿐이었다.
2. 개선 방향이 Macro F1 / M1 F1 / Ordinal MAE / Kappa에서 동시에 일치했다.
3. 목표 failure인 M0↔M1 confusion이 실제로 줄었다.
4. best epoch가 1에서 2~3으로 이동해 optimization behavior도 가설과 같은 방향으로 변했다.

따라서 다음 실험의 방향을 실제로 바꾸는 evidence다.

## Reliability

- 실제 실행 완료: YES
- frozen split checksum: VERIFIED
- test tuning: NO
- structured artifact: YES
- single seed screening: YES
- multi-seed confirmation: **NO**

한 seed의 결과이므로 아직 `검증된 개선` 또는 `PROMOTE_CANDIDATE`로 표현하지 않는다.

## Decision

`KEEP 5e-5 FOR CONFIRMATION`

`1e-4`도 baseline보다 개선되었지만 `5e-5`가 주요 metric과 M1 boundary에서 일관되게 더 좋았다. 따라서 다음 단계에서는 더 많은 LR 값을 추가 탐색하지 않고 **`3e-4` baseline과 `5e-5`만 paired multi-seed로 재검증**한다.

`1e-4`는 별도 추가 실험하지 않는다. 이미 다음 의사결정에 필요한 정보가 충분하기 때문이다.
