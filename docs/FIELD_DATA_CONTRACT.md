# Nongtori Field Data Contract

Status: **SOURCE_WIP / CONTRACT_FROZEN_CANDIDATE**

Google Sheet `딸기_프로젝트`의 현장 데이터 의미를 코드/학습 파이프라인에서 해석하는 계약이다. Sheet는 read-only source로 사용하며 자동 수정/빈값 보완을 금지한다.

## 1. Source tabs

```text
컬럼정보
농가_딸기데이터
농가_베드길이
```

## 2. Header contract

현재 실제 header:

```text
Date, Time_Stamp, ID, Group_ID, Original_No, Weather, Farm, Zone,
Variety, Class, DataType, View_Type, Occlusion, Length, Width, Weight_g,
Maturity, Grade, Amb_Temp, Ref_Temp, Leaf_Temp, Amb_Humi, Light_Level,
Health, Risk_Status, Final_Name
```

## 3. Farm / Location

`Farm` code: `M / C1 / C2 / U`.

원본 `Zone` 예: `숲촌4동-4-A`, `두양4동-5-A`.

원본 값은 source label로 영구 보존한다. parser가 성공한 경우에만 derived field를 만든다.

```text
farm=M
house=숲촌4동
bed=4
zone=A
source_zone=숲촌4동-4-A
```

parse 실패 시 원본을 버리지 않고 `LOCATION_PARSE_ERROR`를 남긴다.

## 4. Group_ID

`Group_ID`는 동일 실제 딸기의 다각도 관측 묶음이다.

```text
same Group_ID
├─ F
└─ RT45
```

동일 Group_ID는 split atomic unit이다.

## 5. View_Type

```text
F    = 정면 관측
RT45 = 수집 당시 임의로 정한 45도 관측
```

목적은 시점 다양성 확보다. `컬럼정보`의 로봇 시점 표현은 legacy collection description이며 **실제 Robot camera installation angle 확정값이 아니다.**

## 6. DataType

- `R`: 일반/RGB
- `T`: 열화상
- `M`: 합성
- `V`: 영상

영상에서 별도 type code를 만들지 않고 `V`를 재사용한다.

## 7. 측정값

`Length`, `Width`, `Weight_g`는 ground truth다.

NULL 처리:
- NULL 자체를 자동 오류로 판정하지 않는다.
- JM 표본은 의도적으로 측정을 생략했을 수 있다.
- size/weight regression에는 target이 있는 행만 eligible하다.
- grade/ripeness task eligibility와 regression eligibility를 분리한다.

## 8. Maturity

- `0`: Green
- `1`: White
- `2`: Turning
- `3`: Mature
- `4`: Full

0~4 체계를 v1에서 유지한다.

## 9. Grade

- `SP`
- `HI`
- `MD`
- `JM`
- `NA`

Sheet `컬럼정보`의 기준은 참고하되 JM을 단일 weight threshold로 재해석하지 않는다. JM은 소과/기형/상품성 저하가 혼재할 수 있다.

## 10. Health

- `NOR`
- `MIT`
- `MIT_R`
- `ANT`
- `MAL`
- `OTH`

`Grade=JM`과 `Health=MAL`은 독립 label이다.

## 11. Environment

`Amb_Temp`, `Ref_Temp`, `Leaf_Temp`, `Amb_Humi`, `Light_Level`은 값이 존재할 때 source unit을 보존하고 normalization에서 단위를 검증한다. 결측을 임의 0으로 대입하지 않는다.

## 12. Video metadata extension

필요 시 source schema를 파괴하지 않고 별도 metadata에 다음을 추가한다.

- `duration`
- `observed_pipe_count`
- `start_anchor`
- `end_anchor`
- `capture_session_id`

철파이프는 Zone 내부 상대 anchor다. 농가마다 간격/개수가 달라질 수 있으므로 공통 거리로 하드코딩하지 않는다.
