# Nongtori Field Data Readiness Policy

Status: **CANONICAL DRAFT / SOURCE-SAFE**
Updated: **2026-09-15**

## Purpose

현재 `딸기_프로젝트` Google Sheet와 사진/영상 원본은 계속 정리 중이다. 따라서 **행이 존재하거나 `Final_Name`이 생성됐다는 이유만으로 학습 가능 데이터로 간주하지 않는다.**

이 문서는 원본을 수정하지 않고 각 row를 학습 준비도 관점에서 분류하는 gate를 정의한다.

## Readiness states

### `READY_METADATA`

학습 task에 필요한 핵심 metadata가 현재 row에 존재하고 enum/range validation도 통과한 상태.

중요: `READY_METADATA`는 **실제 media file이 존재하고 hash 검증까지 끝났다는 뜻이 아니다.** physical asset 검증 전에는 최종 `TRAINING_READY`로 승격하지 않는다.

### `PARTIAL`

현재 정리 중인 row. 예:

- `ID`, `Group_ID`, `Original_No` 일부 누락
- `Farm`, `Class`, `DataType`, `View_Type` 일부 누락
- STR인데 `Maturity`가 아직 비어 있음
- LEF인데 Health/Risk 관련 입력이 아직 정리 중

PARTIAL은 오류가 아니라 **WIP source 상태**다. 자동 삭제/자동 라벨 보정 금지.

### `INVALID_FOR_TRAINING`

현재 값 자체가 canonical rule과 충돌하거나 허용 범위를 벗어난 상태.

예:

- Farm=`C` 저장 (`C`는 grouped scope이며 stored farm code가 아님)
- Maturity가 0~4 범위 밖
- Class가 허용 enum 밖
- Grade가 허용 enum 밖
- DataType / View_Type / Occlusion이 허용 범위 밖

원본은 그대로 보존하고 normalized manifest에서 exclusion reason을 기록한다.

### `TRAINING_READY`

`READY_METADATA`에 더해 아래가 모두 검증된 상태:

1. physical media 존재
2. source↔row matching 성공
3. content SHA-256 계산
4. duplicate/group policy 통과
5. task-specific label policy freeze 통과
6. leakage-safe split group 확보
7. snapshot에 immutable revision으로 편입

현재 field source는 이 단계로 자동 승격하지 않는다.

## Canonical enum/range rules

### Common

- Farm: `M`, `C1`, `C2`, `U`
- Class: `STR`, `LEF`
- DataType: `R`, `T`, `M`, `V`
- View_Type: `RT45`, `F` (현재 정의된 범위)
- Occlusion: `0`, `1`, `2`

### STR

필수 metadata 후보:

- Date
- ID
- Group_ID
- Original_No
- Farm
- Zone
- Variety
- Class=`STR`
- DataType
- View_Type
- Occlusion
- Maturity
- Grade
- Final_Name

Validation:

- Maturity: integer `0..4`
- Grade: `SP`, `HI`, `MD`, `JM`, `NA`

`Length / Width / Weight_g`는 수확·실측 상황에 따라 비어 있을 수 있으므로 전체 STR row의 공통 필수값으로 강제하지 않는다.

### LEF

Maturity는 필수가 아니다.

핵심 metadata 후보:

- Date
- ID
- Group_ID
- Original_No
- Farm
- Zone
- Variety
- Class=`LEF`
- DataType
- View_Type
- Occlusion
- Grade
- Final_Name

Health / Risk_Status / Thermal 관련 값은 병해충 task acceptance에서 별도 gate를 둔다.

## Important semantic distinction

Google Sheet `컬럼정보`에는 현재 Maturity가 `0~4 (Green, White, Turning, Mature, Full)`로 기술되어 있다.

이것은 **현재 source 입력 가이드**이며, 최종 모델 acceptance용 육안 annotation standard는 아직 freeze되지 않았다.

따라서:

- source value는 그대로 보존한다.
- 외부 dataset normalization mapping과 field annotation guideline을 동일시하지 않는다.
- 최종 label definition이 바뀌어도 원본 Sheet row를 덮어쓰지 않는다.
- 새로운 mapping/version을 normalized snapshot에 적용한다.

## Current observed source boundary — 2026-09-15

현재 Sheet에서 ID `0001`~`0110`까지 연속적인 row가 확인된다.

그 이후에는 다음과 같은 WIP row가 존재한다.

- ID 없음
- Group_ID 없음
- Original_No 없음
- 일부 Farm / Zone / Class / DataType / View_Type / Health 값 미완성
- 수식 기반 `Final_Name`은 생성되어 있음

따라서 현재 ingestion에서 **`Final_Name != null`만으로 active row를 판정하면 안 된다.**

권장 active boundary:

```text
row has stable ID + Group_ID + task identity fields
→ readiness evaluation 대상

otherwise
→ PARTIAL / WIP
```

## Known source-quality observations

현재 Sheet audit에서 확인된 예:

1. 동일 `Original_No` 문자열이 서로 다른 row/context에 나타날 수 있음.
   - `Original_No` 단독 unique key 금지.
2. source Date와 `Original_No` 내부 timestamp가 불일치하는 사례가 존재함.
   - 자동 수정 금지, provenance warning으로 기록.
3. 동일 `Group_ID` 아래 RT45/F 다각도 row가 존재함.
   - split 시 동일 Group_ID cross-split 금지.
4. STR와 LEF는 필수 label이 다름.
   - 하나의 공통 `not-null` rule로 검증 금지.

## Output contract for readiness audit

행별 최소 출력:

```text
source_row
id
group_id
class
farm
readiness
reason_codes[]
warnings[]
```

집계:

```text
READY_METADATA
PARTIAL
INVALID_FOR_TRAINING
by_class
by_farm
reason_counts
warning_counts
```

Physical media audit가 연결되면 별도 필드 추가:

```text
asset_status
asset_sha256
source_match_status
duplicate_group
training_ready
```

## Safety

- Google Sheet 수정 금지
- 사진/영상 rename/delete 금지
- 원본 label 자동 보정 금지
- PARTIAL row 자동 삭제 금지
- `C`를 stored Farm으로 생성 금지
- media 존재를 확인하지 않고 `TRAINING_READY` 주장 금지
