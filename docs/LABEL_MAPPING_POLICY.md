# Nongtori Label Mapping Policy

Status: **CANONICAL / FIELD_SEMANTICS_CLARIFIED**

이 문서는 Google Sheet `딸기_프로젝트`의 현장 라벨과 외부 공개 데이터셋의 라벨을 Nongtori 학습용 canonical label로 변환하는 규칙을 정의한다. 원본 Google Sheet schema는 유지하고, 파생 라벨은 Normalize/Manifest 계층에서 생성한다.

## 1. 기본 원칙

1. 원본 라벨은 항상 보존한다.
2. `source label → canonical stage → task label`의 3계층 구조를 사용한다.
3. 현장 데이터의 명시적 의미를 외부 데이터에 무조건 확장하지 않는다.
4. `Grade`로 Harvest target을 만들 수 있지만 Harvest 모델 입력 feature로 `Grade`를 사용하지 않는다. 이는 target leakage다.
5. `JM`, `MAL`, `PROCESSING_JAM`은 서로 다른 의미다.

## 2. Field Grade semantics

Google Sheet 현장 데이터에서는 Grade가 수확 여부를 명시한다.

| Grade | Field 의미 | derived `observed_harvest` |
|---|---|---:|
| `SP` | 실제 수확물 - 특상 | `true` |
| `HI` | 실제 수확물 - 상 | `true` |
| `MD` | 실제 수확물 - 중 | `true` |
| `JM` | 실제 수확물 - 하품/비상품성 계열 | `true` |
| `NA` | 수확하지 않은 개체 | `false` |

따라서 field normalization에서는 다음을 사용한다.

```text
Grade in {SP, HI, MD, JM} → observed_harvest = true
Grade == NA                → observed_harvest = false
```

`NA`는 unknown이 아니다. 후숙도/수확 적기 등의 이유로 수확하지 않은 field sample이다.

## 3. JM / MAL 관계

`Grade=JM`과 `Health=MAL`은 컬럼 의미가 다르다.

- `JM`: 수확물의 상품 등급 결과
- `MAL`: 기형이라는 health/state label

현장 라벨 정책에서는 기형(`Health=MAL`) 과실을 수확했을 경우 Grade는 반드시 `JM`이다.

```text
Health = MAL → Grade = JM
```

그러나 역방향은 성립하지 않는다.

```text
Grade = JM ↛ Health = MAL
```

JM에는 기형 외에도 소과, 과숙, 외관/상품성 저하 등이 포함될 수 있다.

## 4. Maturity와 Harvest의 분리

Maturity는 과실의 숙도 상태이고 Harvest는 실제 수확 행동이다.

Field source에서는 Grade로 실제 Harvest를 파생한다.

특히 `Maturity=3 (Mature)`는 수확/미수확이 모두 가능하다.

```text
Maturity=3 + Grade=SP/HI/MD/JM → 실제 수확
Maturity=3 + Grade=NA          → 미수확
```

따라서 `Maturity=3 → HARVEST` 같은 고정 규칙을 만들지 않는다.

동일하게 `Maturity=4 → JM`도 금지한다. 정상 완숙 과실은 SP/HI/MD가 될 수 있다.

## 5. Canonical phenology

외부 데이터 라벨 정규화를 위해 다음 중간 stage를 사용한다.

- `FLOWER`
- `GREEN_SMALL`
- `GREEN`
- `WHITE`
- `TURNING_EARLY`
- `TURNING_MID`
- `TURNING_LATE`
- `RED_RIPE`
- `OVERRIPE`

Nongtori Maturity 0~4 매핑 기본값:

| Canonical stage | Maturity |
|---|---:|
| `GREEN_SMALL` | 0 |
| `GREEN` | 0 |
| `WHITE` | 1 |
| `TURNING_EARLY` | 2 |
| `TURNING_MID` | 2 |
| `TURNING_LATE` | 3 |
| `RED_RIPE` | 4 |
| `OVERRIPE` | 4 |
| `FLOWER` | `null` |

`TURNING_LATE`는 Maturity 3으로 정규화하지만 Harvest 여부는 별도다.

## 6. OVERRIPE 정책

과숙은 숙도 축에서는 Maturity 4로 보고 상품 등급 축에서는 JM으로 정규화한다.

```text
OVERRIPE
→ canonical_stage = OVERRIPE
→ nongtori_maturity = 4
→ nongtori_grade = JM
→ grade_reason = OVERRIPE
```

그러나 다음 역규칙은 금지한다.

```text
Maturity=4 → Grade=JM    # 금지
Grade=JM → OVERRIPE      # 금지
```

외부 데이터의 `OVERRIPE → Grade=JM`은 Nongtori task label mapping이며, 그 외부 데이터가 실제 농가에서 수확됐다는 `observed_harvest=true` 증거로 사용하지 않는다. `observed_harvest`는 source가 실제 수확 행동을 제공할 때만 생성한다.

## 7. Usage / Jam 분리

`JM`은 `PROCESSING_JAM`과 동의어가 아니다.

```text
Grade / Quality
→ FRESH / PROCESSING_JAM / REJECT
```

용도 판단은 숙도, 크기/무게, 형태, 외관, health, 상품성을 종합한다.

금지:

```text
JM   → JAM
FULL → JAM
```

## 8. External source mapping

외부 source는 원본 label과 세부 metadata를 보존한다.

예시:

```yaml
source_id: DATA-RIP-001
source_label: Late-Turning
canonical_stage: TURNING_LATE
nongtori_maturity: 3
mapping_version: MAP-RIP-001-v1
mapping_confidence: HIGH
mapping_basis: SOURCE_DEFINITION
```

과숙 예시:

```yaml
source_id: DATA-RIP-002
source_label: overripe
canonical_stage: OVERRIPE
nongtori_maturity: 4
nongtori_grade: JM
grade_reason: OVERRIPE
observed_harvest: null
mapping_version: MAP-RIP-002-v1
```

## 9. Mapping confidence

- `HIGH`
- `MEDIUM`
- `LOW`
- `UNMAPPED`

가능한 basis:

- `SOURCE_DEFINITION`
- `DECIMAL_STAGE`
- `COLOR_PERCENT_RANGE`
- `FIELD_POLICY`
- `EMPIRICAL_CALIBRATION`

애매한 외부 label을 데이터 수 증가 목적으로 강제 mapping하지 않는다.

## 10. Google Sheet schema policy

현재 Google Sheet 컬럼을 Label Mapping 편의를 위해 추가/변경하지 않는다.

파생 필드 예:

- `canonical_stage`
- `nongtori_maturity`
- `nongtori_grade`
- `grade_reason`
- `observed_harvest`
- `mapping_version`
- `mapping_confidence`
- `mapping_basis`

이 필드들은 immutable normalized manifest/snapshot에 생성한다.

Google Sheet schema 변경은 현장 원본만으로 표현할 수 없는 새로운 ground truth가 실제로 필요할 때만 검토한다.
