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

이 실험을 통해 실제로 확인된 정보는 다음과 같다.

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

따라서 이 결과는 **재현 가능한 기준선**으로는 충분하지만, 운영 모델의 신뢰성을 입증한 결과는 아니다.

## Decision

`KEEP AS REPRODUCED BASELINE`

이 모델은 배포 후보로 채택한 것이 아니라 이후 모든 개선 실험의 비교 기준선으로 유지한다.

## Next Action

다음 실험은 현재 결과에서 확인된 **epoch 1 peak / M0↔M1 경계 혼동** 중 하나를 직접 검증하는 통제 실험만 수행한다.

실제 실행 결과가 나오기 전에는 이 문서에 새 실험 항목을 추가하지 않는다.
