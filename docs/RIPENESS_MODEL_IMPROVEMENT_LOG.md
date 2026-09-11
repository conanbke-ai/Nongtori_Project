# Nongtori Ripeness Model Improvement Log

Status: **CANONICAL / REQUIRED**

이 문서는 Nongtori 숙도 모델의 개선 과정을 재현 가능하게 기록하기 위한 실험 의사결정 로그다. 이후 모든 후보 모델/튜닝 실험은 단순 성능 수치가 아니라 **문제 관찰 → 원인 가설 → 조정 → 결과 → 비교 → 채택/기각 → 다음 단계** 흐름으로 기록한다.

---

## 1. 기록 원칙

각 실험은 반드시 아래 순서로 기록한다.

1. **Baseline / Current State**
   - 기준 snapshot
   - 기준 모델/config
   - 기준 metric
   - 주요 failure pattern

2. **Observed Problem**
   - 어떤 현상이 문제였는가
   - 어떤 class / metric / learning curve에서 드러났는가

3. **Hypothesis**
   - 왜 이런 문제가 발생했다고 보는가
   - 데이터 문제 / optimization 문제 / architecture 문제 / label 문제 중 어디에 가까운가

4. **Change Applied**
   - 정확히 무엇을 바꿨는가
   - learning rate, optimizer, scheduler, augmentation, backbone, loss, fine-tuning policy 등

5. **Experiment Controls**
   - 동일 snapshot / split 유지 여부
   - seed
   - test set 사용 여부
   - 변경한 항목과 고정한 항목

6. **Result**
   - validation metric
   - test metric은 후보 config freeze 후에만 기록
   - class별 metric / confusion matrix
   - train/valid loss curve
   - runtime / checkpoint

7. **Delta vs Baseline**
   - 절대값 변화
   - 상대 개선율
   - 좋아진 class / 나빠진 class

8. **Decision**
   - KEEP / REJECT / RETEST / PROMOTE_CANDIDATE
   - 이유

9. **Next Action**
   - 다음 실험에서 무엇을 검증할지

---

# 2. Baseline V001

## Baseline identity

- Experiment: `RIPENESS-BASELINE-V001`
- Snapshot: `KGCV-RIPENESS-V001`
- Assignment SHA-256: `5e2424f7c26d84e4f8d43ca90ba60b46806eb9d7bb361669c8b42ad27f2040ea`
- Model: ImageNet-pretrained ResNet-18
- Fine tuning: full backbone trainable from epoch 1
- Optimizer: AdamW
- Learning rate: `3e-4`
- Weight decay: `1e-4`
- Batch size: 32
- Early stopping: validation Macro F1, patience 5
- Train samples: 2,243
- Valid samples: 486
- Test samples: 433

## Baseline result

| Metric | Result |
|---|---:|
| Best valid Macro F1 | 0.9536944102 |
| Test Accuracy | 0.9422632794 |
| Test Macro F1 | 0.9402391674 |
| Test Ordinal MAE | 0.0900692841 |
| Test Weighted Kappa | 0.9419644636 |

### Per-class F1

| Maturity | F1 |
|---|---:|
| M0 | 0.9368421053 |
| M1 | **0.9023255814** |
| M4 | 0.9815498155 |

### Primary failure pattern

Confusion matrix, rows=true / columns=predicted, order `[0, 1, 4]`:

```text
[[178, 14,  4],
 [  6, 97,  0],
 [  0,  1,133]]
```

Observed failures:

- M0 → M1: 14
- M0 → M4: 4
- M1 → M0: 6
- M4 → M1: 1

The dominant issue is **M0 / M1 boundary confusion**.

## Learning behavior

- Best validation checkpoint: epoch 1
- Early stopping: epoch 6
- Later epochs did not beat epoch 1 despite continued optimization

Interpretation:

- full-network fine tuning with LR `3e-4` is likely too aggressive
- the pretrained backbone may be forgetting useful ImageNet features too quickly
- current augmentation / loss may not sufficiently stabilize the M0↔M1 boundary
- model capacity is not obviously the first bottleneck because M4 performance is already very strong

Decision:

`REFERENCE → REPRODUCED`

This model is kept as the reproducible comparison baseline, not as a deployment candidate.

---

# 3. Improvement Plan V002

The next experiments must use the **same frozen snapshot and validation split**. The test split must not be used to select hyperparameters.

## Experiment A — Lower full fine-tuning learning rate

### Observed Problem

Best checkpoint appears at epoch 1 and validation does not improve afterward.

### Hypothesis

The full backbone LR `3e-4` is too high for transfer learning and causes rapid overfitting / catastrophic forgetting.

### Change

Compare:

```text
A1: lr = 1e-4
A2: lr = 5e-5
```

All other variables remain fixed.

### Expected signal

- best epoch should move later than epoch 1
- validation Macro F1 should remain stable or improve
- M1 F1 should improve without M4 degradation
- train/valid divergence should reduce

### Acceptance

Promising if validation Macro F1 improves and M1 F1 rises with no material degradation in ordinal MAE / weighted kappa.

---

## Experiment B — Two-stage fine tuning

### Observed Problem

Immediate full-backbone training appears unstable.

### Hypothesis

The classifier head needs to adapt to strawberry-specific features before the pretrained backbone is updated.

### Change

Stage 1:

```text
freeze backbone
train classifier head only
2~5 epochs
```

Stage 2:

```text
unfreeze final ResNet block first
then optionally full backbone
use lower LR for backbone than head
```

Suggested discriminative LR:

```text
head: 1e-4
backbone: 1e-5 ~ 5e-5
```

### Expected signal

- validation peak later and more stable
- lower overfitting rate
- improved M0/M1 separation

---

## Experiment C — Scheduler

### Hypothesis

A fixed LR may be too coarse once the pretrained model reaches a useful basin quickly.

### Candidate

- cosine annealing
- `ReduceLROnPlateau(valid_macro_f1)`

### Decision rule

Scheduler must improve validation stability, not merely lower train loss.

---

## Experiment D — Loss adjustment

Only run after A/B/C if M0↔M1 confusion remains.

Candidate:

- label smoothing cross entropy
- focal loss

Reason:

The problem is not severe global class imbalance alone; the main issue is a specific adjacent-stage decision boundary. Therefore loss replacement is not the first intervention.

---

## Experiment E — Backbone comparison

Run only after the training recipe is stabilized so architecture and optimization are not confounded.

Candidate backbones:

1. ResNet-18 baseline
2. EfficientNet-B0
3. ConvNeXt-Tiny, subject to runtime budget

Evaluation dimensions:

- validation Macro F1
- M1 F1
- Ordinal MAE
- Weighted Kappa
- inference latency
- model size
- CPU/GPU runtime

A heavier model is not selected merely for a small accuracy gain.

---

# 4. Candidate Promotion Rules

A candidate can be promoted only if:

1. it uses the exact frozen `KGCV-RIPENESS-V001` train/valid assignment
2. test is not used for tuning
3. result is reproducible with recorded seed/config/checkpoint
4. validation Macro F1 improves over baseline or provides a meaningful class-specific improvement
5. Maturity 1 behavior improves without serious degradation to M0 / M4
6. Ordinal MAE and Weighted Kappa do not regress materially
7. learning behavior is more stable than baseline

After a configuration is frozen, it may be evaluated once on the fixed test set and compared against:

```text
Baseline Test Macro F1      0.9402391674
Baseline Test Ordinal MAE   0.0900692841
Baseline Test Kappa         0.9419644636
Baseline M1 F1              0.9023255814
```

---

# 5. Experiment Record Template

Copy this block for every experiment.

```markdown
## EXP-XXX — <name>

### Baseline / Current State
- snapshot:
- parent experiment:
- parent metrics:

### Observed Problem

### Hypothesis

### Change Applied

### Controlled Variables
- snapshot:
- split:
- seed:
- unchanged config:

### Validation Result
| Metric | Baseline | Experiment | Delta |
|---|---:|---:|---:|
| Macro F1 | | | |
| M0 F1 | | | |
| M1 F1 | | | |
| M4 F1 | | | |
| Ordinal MAE | | | |
| Weighted Kappa | | | |

### Learning Behavior
- best epoch:
- early stop epoch:
- train/valid loss behavior:
- checkpoint SHA-256:

### Failure Analysis

### Decision
KEEP / REJECT / RETEST / PROMOTE_CANDIDATE

### Reason

### Next Action
```

---

# 6. Portfolio Narrative Rule

When summarizing this project externally, use this structure:

```text
Baseline에서 Maturity 1 F1이 약 0.90이고 M0→M1 오분류가 주요 실패 패턴이었다.
또한 validation best가 epoch 1에서 발생해 full fine-tuning LR이 과도하다고 판단했다.

따라서 learning rate 축소와 단계적 unfreeze를 우선 적용하고,
동일 frozen split에서 validation Macro F1 / M1 F1 / Ordinal MAE / Kappa를 비교했다.

개선안은 test set을 사용하지 않고 validation으로만 선택한 후,
최종 선택된 configuration만 frozen test set에서 평가했다.

이 과정을 통해 단순 정확도 경쟁이 아니라
오류 패턴 분석 → 가설 → 통제 실험 → 재현 가능한 모델 선택 과정을 구축했다.
```

이 문서의 목적은 모델 성능 수치 자체보다 **왜 변경했고, 어떤 근거로 유지/폐기했는지**를 남기는 것이다.
