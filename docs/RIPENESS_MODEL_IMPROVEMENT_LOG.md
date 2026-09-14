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

# EXP-RIP-002 — Lower Full-Fine-Tuning LR

Status: **CONFIRMED OPTIMIZATION IMPROVEMENT / VALIDATION ONLY**

## Screening Evidence

- Initial GitHub Actions run: `34561786597`
- Structured run id: `f7a06f1bd8bd`
- Snapshot: `KGCV-RIPENESS-V001`
- Seed: `20260910`
- Test evaluated: **NO**
- Compared variable: learning rate only
- Fixed: model, optimizer family, weight decay, batch size, augmentation, snapshot, split, class weighting, early-stopping rule

## Observed Problem

Baseline LR `3e-4`에서 validation best가 지나치게 빠르게 발생하고 M0/M1 경계 혼동이 컸다.

## Hypothesis

**full-backbone learning rate를 낮추면 optimization이 안정화되고 숙도 경계 성능 및 seed 안정성이 개선될 수 있다.**

## Initial Screening Result

| Metric | Baseline `3e-4` | `1e-4` | `5e-5` |
|---|---:|---:|---:|
| Macro F1 | 0.953694 | 0.969563 | **0.971656** |
| M1 F1 | 0.917749 | 0.946903 | **0.951111** |
| Ordinal MAE ↓ | 0.067901 | 0.045267 | **0.043210** |
| Weighted Kappa | 0.960312 | 0.970794 | **0.972190** |
| Best epoch | 1 | 3 | 2 |

Failure pattern도 `M0 → M1: 12 → 7`로 감소했다. 이 결과를 근거로 `1e-4` 추가 탐색은 중단하고 `5e-5`만 confirmation 대상으로 승격했다.

## Paired Multi-seed Confirmation

GitHub Actions run: `34605181173`

Seeds:
- `20260911`
- `20260912`
- `20260913`

각 seed에서 `3e-4`와 `5e-5`를 동일한 snapshot/split/augmentation/optimizer 조건으로 paired 비교했고, test set은 열지 않았다.

### Seed별 best validation 결과

| Seed | LR | Macro F1 | Ordinal MAE ↓ | Weighted Kappa | Best Epoch |
|---|---:|---:|---:|---:|---:|
| 20260911 | 3e-4 | 0.9596 | 0.0453 | 0.9677 | 5 |
| 20260911 | 5e-5 | **0.9644** | **0.0432** | **0.9724** | 6 |
| 20260912 | 3e-4 | **0.9653** | **0.0453** | 0.9680 | 12 |
| 20260912 | 5e-5 | 0.9607 | 0.0473 | **0.9693** | 9 |
| 20260913 | 3e-4 | 0.9528 | 0.0556 | 0.9632 | 6 |
| 20260913 | 5e-5 | **0.9624** | **0.0453** | **0.9710** | 5 |

`5e-5`가 모든 seed에서 모든 metric을 이긴 것은 아니다. seed `20260912`에서는 Macro F1과 MAE가 `3e-4`에 소폭 뒤졌다. 따라서 이 실험을 "모든 실행에서 절대 우세"라고 해석하지 않는다.

### 3-seed aggregate

| Metric | `3e-4` mean ± std | `5e-5` mean ± std | Mean Δ |
|---|---:|---:|---:|
| Macro F1 | 0.9592 ± 0.0063 | **0.9625 ± 0.0019** | **+0.0033** |
| Ordinal MAE ↓ | 0.0487 ± 0.0059 | **0.0453 ± 0.0021** | **-0.0035** |
| Weighted Kappa | 0.9663 ± 0.0027 | **0.9709 ± 0.0016** | **+0.0046** |

## Interpretation

이 confirmation에서 가장 중요한 정보는 단순 평균 상승만이 아니다.

1. Macro F1 평균이 상승했다.
2. Ordinal MAE 평균이 감소했다.
3. Weighted Kappa 평균이 상승했다.
4. Macro F1 표준편차가 약 `0.0063 → 0.0019`로 크게 감소했다.
5. MAE와 Kappa의 seed 간 변동도 감소했다.
6. 즉 `5e-5`는 baseline보다 **평균적으로 조금 더 좋고, 훨씬 더 안정적인 optimization recipe**였다.

따라서 초기 screening에서 관찰한 개선 방향이 단일 seed 우연만으로 설명되지는 않는다.

다만 이 confirmation은 validation-only이고 KGCV M0/M1/M4 외부 데이터에 한정되어 있다. 이 결과만으로 production reliability 또는 field reliability를 주장하지 않는다.

## Reliability

- 실제 screening 실행: YES
- paired 3-seed confirmation: YES
- frozen split checksum: VERIFIED
- test tuning: NO
- structured artifacts: YES
- aggregate mean/std: YES
- field validation: NO

## Decision

`CONFIRMED: USE LR 5e-5 AS CURRENT RESNET-18 FULL-FINETUNING RECIPE`

`5e-5`를 현재 ResNet-18 full fine-tuning의 기본 LR로 승격한다.

이 결정은 "최종 숙도 모델 확정"이 아니라 **optimization recipe 하나가 baseline 대비 검증되었다**는 의미다.

다음 개선 실험은 LR을 더 촘촘하게 스윕하지 않는다. 이미 의사결정에 충분한 evidence가 있으므로, 다음에는 다른 원인 축을 하나만 선택해 통제 실험한다.
