# Nongtori AI Decision Policy

이 문서는 AI 분석 결과가 실제 농작업 의사결정으로 이어지는 방식을 정의한다.

## 1. 기본 정책

| 영역 | 정책 | 정상 흐름 사람 확인 |
|---|---|---|
| 병해충/응애 | `ALERT_AND_VERIFY` | 허용/필요 |
| 숙도 | `AUTO_DECIDE` | 없음 |
| 상품 등급/품질 | `AUTO_DECIDE` | 없음 |
| 출하/가공/제외 용도 | `AUTO_DECIDE` | 없음 |
| 카메라/모델/데이터 이상 | `SYSTEM_EXCEPTION` | 예외적으로 필요 |

농토리는 사람이 딸기마다 AI 결과를 재검수하는 시스템으로 만들지 않는다.

## 2. 과실 판단 흐름

```text
Fruit Detection
→ Tracking
→ Multi-frame Ripeness
→ Harvest Decision
→ Quality / Grade
→ FRESH / PROCESSING_JAM / REJECT
```

낮은 confidence 한 프레임만으로 사람을 호출하지 않는다.

```text
low confidence
→ 추가 frame 관측
→ temporal aggregation
→ 여전히 실패
→ SYSTEM_EXCEPTION
```

## 3. 숙도

Maturity 0~4를 유지한다.

- 0 Green
- 1 White
- 2 Turning
- 3 Mature
- 4 Full

단일 frame보다 track-level multi-frame aggregation을 우선한다.

숙도와 실제 수확 행동은 같은 target이 아니다. 특히 `Maturity=3`에서도 수확/미수확 사례가 모두 존재할 수 있으므로 `Maturity=3 → HARVEST` 같은 고정 규칙을 금지한다.

외부 label normalization은 `LABEL_MAPPING_POLICY.md`를 따른다. 핵심 기본값은 다음과 같다.

```text
TURNING_LATE → Maturity 3
RED_RIPE     → Maturity 4
OVERRIPE     → Maturity 4
```

## 4. Field Harvest ground truth

Google Sheet 현장 데이터에서는 `Grade`가 실제 수확 여부를 명시한다.

```text
Grade in {SP, HI, MD, JM} → 실제 수확
Grade == NA                → 미수확
```

Normalize/Manifest에서는 이를 `observed_harvest` target으로 파생한다.

Harvest Decision 모델에서 `Grade`를 input feature로 넣지 않는다. Grade로 target을 생성하면서 Grade를 feature로 사용하면 target leakage다.

## 5. 등급 / 용도

`FULL = JAM` 같은 단순 매핑을 금지한다. 가공/출하 판단은 다음을 종합한다.

- 숙도
- 크기/무게
- 형태
- 외관
- 병징/health
- 상품성

`Grade=JM`과 `Health=MAL`은 동치가 아니다.

- `JM`: 실제 수확물의 하품/상품성 저하 등급
- `MAL`: 기형이라는 health/state

현장 라벨 정책에서는 기형 과실을 수확한 경우 반드시 `Grade=JM`이다.

```text
Health=MAL → Grade=JM
Grade=JM  ↛ Health=MAL
```

외부 `OVERRIPE`는 Nongtori task label에서 다음처럼 정규화한다.

```text
OVERRIPE
→ Maturity = 4
→ Grade = JM
→ grade_reason = OVERRIPE
```

그러나 다음 역규칙은 금지한다.

```text
Maturity=4 → JM
JM → OVERRIPE
```

`JM`은 `PROCESSING_JAM`과 동일하지 않다. 소과/기형/과숙/기타 상품성 저하가 모두 포함될 수 있으므로 최종 용도는 별도 판단한다.

## 6. 병해충

병해충은 위험비용 때문에 자동 확정 처방보다 구역 검증을 포함한다.

```text
AI evidence
→ risk aggregation
→ zone alert
→ VERIFY_ZONE
→ confirmed / rejected / recheck
```

검증된 inference capability가 없는 병해충은 `RECORD_ONLY`로 둘 수 있으며 confidence/결과를 가짜로 생성하지 않는다.

## 7. 시스템 예외

다음은 `SYSTEM_EXCEPTION` 대상이다.

- 모델/weight unavailable
- 입력 frame 부족
- data contract violation
- source/API unavailable
- unit normalization failure
- out-of-distribution

실패를 정상 label/가격/confidence로 덮지 않는다.

## 8. UI 계약

정상 결과는 `결과 → 근거 → 행동` 순서로 보여준다. 시스템 예외는 기술 스택 메시지보다 재촬영/재시도/관리자 확인 등 사용자가 취할 행동을 우선 제시한다.
