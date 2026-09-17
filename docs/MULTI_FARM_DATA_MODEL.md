# 다농가 운영 데이터 모델

## 역할 분리

- 업체 운영자/데이터 관리자: 농가, 공간구조, 품종, 카메라 연결을 등록하고 데이터 수집·정리·revision 상태를 관리한다.
- 농민/작업자: 자동수확로봇을 운용하거나 직접 촬영 판독을 실행하고 결과를 확인한다.
- 서비스: 영상 세션, 프레임 번호, 객체 추적 ID, RGB·열화상 대응 관계와 ingestion provenance/revision을 자동 생성한다.

농민용 화면이나 요청에서는 내부 ID를 입력받지 않는다. 원본 파일명 정리, revision ledger, manifest, dedup/split, snapshot 등 데이터 엔지니어링 기능은 운영자 `데이터 관리센터`의 책임이다.

## 공간 모델 원칙

농토리는 모든 농가를 `농가 → 동 → 베드 → 구역` 고정 계층으로 가정하지 않는다.

현장 구조는 농가마다 다를 수 있다.

- M 계열 농가: 여러 하우스/동이 분리되어 있고 각 동 안에 베드가 존재할 수 있음
- C1 계열 농가: 대형 일체형 시설이 둘 이상으로 나뉠 수 있음
- C2 계열 농가: 하나의 큰 스마트팜 내부를 베드/열/구역 중심으로 관리할 수 있음

따라서 canonical 위치 구조는 가변 계층형 `spatial_units`로 정의한다.

```text
Farm
└─ SpatialUnit (optional parent)
   └─ SpatialUnit
      └─ ...
         └─ 관리/관측 단위 SpatialUnit
```

`SpatialUnit.type` 후보:

```text
FACILITY
HOUSE
SECTION
BLOCK
BED
ROW
ZONE
CUSTOM
```

`HOUSE`는 선택 가능한 공간 유형 중 하나이며 모든 농가의 필수 단계가 아니다.

예시:

```text
M 농가
└─ HOUSE: 3동
   └─ BED: 08
      └─ ZONE: E

C1 농가
└─ FACILITY: A
   └─ BED: 37
      └─ ZONE: E

C2 농가
└─ BED: 37
   └─ ZONE: E
```

사용자 화면에서는 전체 내부 계층보다 농가에서 실제 사용하는 표시코드(`C2-37-E` 등)를 우선한다.

## 관계형 데이터 구조

목표 구조:

```text
farms
├─ farm_members
├─ farm_items ─ crop_types / cultivars
├─ farm_cultivars ─ cultivars
├─ spatial_units
│  └─ parent spatial_unit_id (nullable)
├─ cameras
└─ capture_sessions
   ├─ spatial_unit_id (nullable)
   ├─ capture_assets
   ├─ video_assets
   │  └─ frames
   └─ inference_runs
      └─ frame_predictions
```

현재 runtime에 `houses / beds / zones` 또는 `house_id / bed_id / zone_id`가 존재하더라도 이는 legacy/compatibility 구조다. 가변 공간계층 전환은 별도 migration으로 수행하며, 포트폴리오 V1 완성을 위해 즉시 destructive migration을 요구하지 않는다.

`capture_sessions`는 로봇 운행 또는 직접 촬영/데이터 정리 1회를 나타내는 핵심 데이터 경계다.

## 위치 식별 계약

자동 관측과 병해충 CASE는 가능한 경우 하나의 `spatial_unit_id`를 authoritative 위치 참조로 사용한다.

```text
farm_id
+ spatial_unit_id
```

원본 데이터의 `Farm`, `Zone`, 기존 house/bed/zone 값은 provenance로 보존한다.

```text
source Farm / Zone / legacy location fields
→ Location Adapter
→ spatial_unit_id
→ display_code / ancestry
```

위치 매핑을 할 수 없는 원본은 임의로 동/베드/구역을 추정 생성하지 않고 unresolved 상태로 둔다.

## 공간 인접성

병해충 의심구역 묶음/확산 판단은 `같은 동`이라는 고정 조건이 아니라 실제 공간 인접성을 기준으로 한다.

V1에서 가능한 최소 기준:

- 같은 parent spatial unit
- 정렬 가능한 bed/row 순서
- zone side/position
- 명시적 adjacency metadata

향후 로봇/시설 좌표를 확보하면 다음을 optional metadata로 확장할 수 있다.

```text
lane
position
side
x/y coordinate
robot_waypoint
```

V1 포트폴리오 범위에서는 로봇 최단경로/SLAM/자동 작업배정까지 구현하지 않는다.

## 다농가 Data Ingestion 경계

모든 데이터 정리 작업은 최소 `farm_id + capture_session_id` 범위에서 수행한다.

```text
Farm
└─ Capture Session
   ├─ Date / Time
   ├─ Spatial Unit / source location
   ├─ Crop / Variety
   ├─ DataType
   └─ Assets / Metadata / Revisions
```

금지:
- 여러 농가 파일을 하나의 rename/audit job에 혼합
- 서로 다른 capture session의 파일을 count만 맞는다는 이유로 일괄 순서 매칭
- filename 안의 Farm 코드만으로 데이터 소유 경계를 대신함

## Incremental Ingestion

최초 1회 전체 기준선을 만든 뒤 이후에는 source 전체를 비교용으로 읽고 변경분만 저장한다.

```text
NEW        → 신규 revision 추가
UNCHANGED  → 저장/복사 없음
UPDATED    → 기존 revision SUPERSEDED + 새 revision ACTIVE
REMOVED    → 물리 삭제하지 않고 REMOVED_FROM_SOURCE
INVALID    → 원본 보존 + 오류 상태
```

행 식별은 안정적인 `source_key`와 `row_hash`를 사용한다.

기본:

```text
source_key = farm_id + ':' + ID
```

필요 시:

```text
source_key = farm_id + ':' + capture_session_id + ':' + ID
```

변경 행은 `changed_fields` diff를 저장해 어떤 값이 바뀌었는지 운영자 화면에서 확인할 수 있게 한다.

## Asset Versioning

사진/영상은 `content_sha256` 기준으로 재사용한다.

- 새 hash: working asset store에 저장
- 기존 hash: 재복사 없이 기존 asset 참조
- 같은 Original_No인데 hash 변경: `SAME_SOURCE_NAME_CONTENT_CHANGED`, 기존 asset SUPERSEDED + 새 revision ACTIVE

원본 파일은 자동 덮어쓰기/rename하지 않는다.

## Google Sheets 가져오기

Google Sheet는 `READ_ONLY` canonical source다.

매번 전체 `.xlsx` 사본을 저장하지 않고 source scan/change detection으로 반영한다. 필요할 때만 baseline/checkpoint full export를 생성한다.

```text
Google Sheet Canonical Source
→ Source Scan
→ Change Detection
→ Revision Ledger
→ Normalize / Dedup / Split
→ Training Snapshot Manifest
```

실제 private source/revision payload는 Git에 올리지 않고 checksum, schema/version, aggregate audit만 저장한다.

## 사진 파일명

현장 사진의 `Final_Name` 적용은 운영자 데이터 관리 기능이다.

기본 정책:
- `Original_No exact` 우선
- EXIF timestamp 보조
- natural order는 fallback
- mismatch/누락/초과/중복 target이 있으면 rename 중단
- 동일 content hash가 이미 validated working asset이면 다시 복사/rename하지 않음

상세 규칙은 `DATA_INGESTION_MANAGEMENT.md`를 따른다.

## Training Snapshot

Training Snapshot은 파일 전체 복사본이 아니라 해당 시점의 **ACTIVE revision + asset hash 집합**을 고정한다.

```text
latest eligible ACTIVE revisions
→ normalize
→ dedup
→ split
→ immutable snapshot manifest
```

과거 revision은 보존하므로 이전 모델 실험도 재현할 수 있다.

## 운영자 데이터 관리센터

운영자는 농가별로 다음을 조회/관리한다.

```text
농가
→ 공간구조
→ 수집 세션
→ NEW / UPDATED / REMOVED / INVALID
→ 사진 / 영상 / 센서
→ file-metadata audit
→ Revision 이력 / changed fields
→ rename manifest
→ Dataset / Snapshot 상태
```

농민 화면에는 Original_No, revision ledger, rename manifest, split hash 같은 내부 데이터 정리 세부를 기본 노출하지 않는다.