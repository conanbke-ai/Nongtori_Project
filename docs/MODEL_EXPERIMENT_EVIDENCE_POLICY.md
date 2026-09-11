# Nongtori Model Experiment Evidence Policy

Status: **CANONICAL / REQUIRED**

이 문서는 모델 개선 문서에 어떤 실험을 기록할 수 있는지 정의한다.

핵심 원칙:

> **개선 문서는 계획서가 아니라 실제 실험에서 얻은 유의미한 증거의 기록이다.**

`해볼 수 있는 설정`, `아직 실행하지 않은 후보`, `단순 재시도`, `똑같은 실패의 반복`은 개선 이력에 기록하지 않는다.

---

## 1. 개선 이력에 기록할 수 있는 조건

한 실험을 개선 이력에 남기려면 최소 다음 증거가 있어야 한다.

1. 실제 실행 완료
2. 실행 ID 또는 재현 가능한 run identity
3. 사용한 snapshot / split / seed / config 기록
4. 변경 전 baseline 명확
5. 변경한 항목 명확
6. validation 결과 존재
7. 비교 metric 존재
8. 로그 또는 artifact 존재
9. 결과를 통해 새로운 판단을 할 수 있음

즉 아래 형태가 되어야 한다.

```text
관찰된 문제
→ 원인 가설
→ 통제된 변경
→ 실제 실행
→ 결과 비교
→ 해석
→ 채택/기각
```

실제 실행이 없는 내용은 `MODEL_IMPROVEMENT_STRATEGY.md`의 전략/가이드에만 존재할 수 있으며, `*_MODEL_IMPROVEMENT_LOG.md`에는 들어가지 않는다.

---

## 2. 기록하지 않는 실험

다음은 원본 run log에는 남더라도 개선 문서에는 개별 항목으로 기록하지 않는다.

### 단순 재시도

예:

- HTTP 502 때문에 동일 조건 재실행
- runner 실패로 동일 job 재실행
- dependency 설치 실패 후 동일 실험 재실행

모델에 대한 새로운 사실이 아니므로 개선 실험으로 취급하지 않는다.

### 결과가 완전히 중복되는 반복

동일한 원인, 동일한 설정, 동일한 결론을 반복한 경우 개별 서술하지 않는다.

필요하면 다음처럼 한 줄로 요약한다.

```text
동일 조건 반복 3회에서 동일 failure pattern 확인; 개별 run은 raw artifact 참조.
```

### 목적 없는 parameter sweep

`일단 1e-3, 1e-4, 1e-5 다 돌려봄` 같은 방식은 지양한다.

각 parameter 변경은 관찰된 문제와 연결된 가설이 있어야 한다.

### metric 차이가 의미 없는 경우

작은 수치 변동만 있고 failure pattern, 안정성, resource cost 등에서 새로운 정보가 없다면 개선 이력의 핵심 항목으로 남기지 않는다.

### 실패 원인이 모델과 무관한 경우

- 네트워크 오류
- disk full
- package conflict
- CI timeout

이런 내용은 운영/실행 로그에만 남기고 모델 개선 로그에는 남기지 않는다.

---

## 3. 의미 있는 실패는 기록한다

실패했다고 모두 제외하는 것은 아니다.

다음과 같이 **모델에 대한 새로운 정보를 준 실패**는 기록한다.

예:

```text
LR을 낮췄더니 overall Macro F1은 유지되었으나 M1 recall이 크게 하락했다.
→ 단순 LR 축소만으로 boundary confusion은 해결되지 않는다는 근거가 됨.
```

또는:

```text
더 큰 backbone에서 validation metric은 소폭 상승했으나 inference latency가 3배 증가했다.
→ 운영 trade-off 때문에 REJECT.
```

이런 결과는 다음 의사결정을 바꾸므로 유의미한 evidence다.

---

## 4. 한 번의 상승을 곧바로 개선으로 확정하지 않는다

### Screening

새 조건의 첫 실행은 `SCREENING`으로 본다.

목적:
- 개선 가능성이 있는지 빠르게 확인
- failure pattern이 실제로 줄었는지 확인

SCREENING 결과만으로 `검증된 성능 개선`이라고 표현하지 않는다.

### Confirmation

`PROMOTE_CANDIDATE`를 고려하는 실험은 다음 중 하나 이상을 추가한다.

1. 동일 config를 복수 seed로 재실행(권장: 3 seeds)
2. 고정 prediction에 대한 bootstrap confidence interval
3. 모델/metric 특성에 맞는 통계적 비교

최종 문서에는 가능하면:

```text
mean ± std
또는
95% confidence interval
```

을 기록한다.

단순히 `0.940 → 0.944` 한 번 상승한 것만으로 유의미한 개선이라고 판단하지 않는다.

---

## 5. Test set 사용 원칙

개선 실험의 반복 비교에는 validation set을 사용한다.

```text
Baseline
→ hypothesis
→ validation experiments
→ candidate freeze
→ confirmation
→ final test
```

고정 test set을 반복 확인하면서 tuning하지 않는다.

Test 결과는 최종 config를 동결한 candidate에 대해서만 사용한다.

---

## 6. 변경 변수 통제

원인 파악이 목적이면 한 실험에서 가능한 한 핵심 변수 하나만 바꾼다.

좋은 예:

```text
Baseline과 동일
learning_rate만 3e-4 → 1e-4
```

나쁜 예:

```text
backbone 변경
LR 변경
augmentation 변경
loss 변경
batch size 변경
→ 결과 상승
```

여러 항목을 동시에 바꾸는 실험은 어떤 변경이 효과를 냈는지 설명할 수 없다.

복합 recipe를 시험할 경우 각 구성요소가 이미 단독 실험으로 검증되었거나, ablation 계획이 있어야 한다.

---

## 7. 실제 개선 이력의 최소 기록 형식

```markdown
## EXP-XXX — <실제 실행된 실험명>

### Evidence
- run id:
- artifact:
- snapshot:
- seed(s):
- checkpoint:

### Observed Problem

### Hypothesis

### Controlled Change
- changed:
- unchanged:

### Actual Result
| Metric | Baseline | Experiment | Delta |
|---|---:|---:|---:|

### Failure Pattern Comparison

### Reliability
- screening / confirmed
- repeat seeds / CI if applicable

### Conclusion
- 무엇을 새로 알게 되었는가

### Decision
KEEP / REJECT / RETEST / PROMOTE_CANDIDATE
```

`Next Action`은 한 줄 정도의 의사결정만 허용하며, 아직 실행하지 않은 수많은 parameter 후보를 실험 결과처럼 나열하지 않는다.

---

## 8. 문서 계층

```text
MODEL_IMPROVEMENT_STRATEGY.md
    └─ 어떤 문제에 어떤 종류의 개선 방법을 검토할지 설명하는 전략 문서

MODEL_EXPERIMENT_EVIDENCE_POLICY.md
    └─ 어떤 실험만 실제 개선 이력에 기록할지 정의

<RIPENESS|PEST|DETECTION|TRACKING|PRICE>_MODEL_IMPROVEMENT_LOG.md
    └─ 실제 실행 + 유의미한 결과만 기록

Raw run artifact / events.jsonl / metrics.json
    └─ 모든 실행의 원본 근거
```

따라서 실험 로그 문서는 CI 실행 내역 전체를 복사하는 장소가 아니다.

---

## 9. Portfolio 기준

최종 포트폴리오에서 강조할 것은 실험 횟수가 아니다.

다음과 같은 흐름만 남긴다.

```text
문제 발견
→ 원인을 데이터로 확인
→ 필요한 변수만 조정
→ 동일 조건에서 비교
→ 유의미한 개선 확인
→ 재현성 검증
→ 최종 모델 선택
```

의미 없는 시행착오 30개보다, 의사결정을 실제로 바꾼 실험 5개가 더 가치 있는 기록이다.
