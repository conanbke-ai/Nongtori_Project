# Nongtori Source Asset ↔ Sample Relation

Status: **CANONICAL / DESIGN_FROZEN**

이 문서는 현장 metadata row와 실제 사진/영상 파일의 관계를 정의한다. `DATA_INGESTION_MANAGEMENT.md`의 파일 매칭 정책을 보완하며, 충돌 시 이 문서의 many-to-one 규칙을 우선한다.

## 1. 핵심 결정

`metadata row = physical file`을 가정하지 않는다.

```text
SourceAsset (physical image/video)
   ├─ SampleRow A
   ├─ SampleRow B
   └─ SampleRow C
```

한 장의 사진에 여러 분석 대상이 존재할 수 있으므로 **하나의 source asset이 여러 sample row에 참조되는 many-to-one 관계를 허용**한다.

반대로 한 sample row가 여러 독립 source asset을 암묵적으로 가리키는 것은 허용하지 않는다. RGB/Thermal pairing처럼 여러 asset이 필요한 경우 명시적 pairing/domain relation을 사용한다.

## 2. 식별자 분리

### Sample identity

```text
sample_id = Sheet.ID
source_key = farm_id + ':' + sample_id
```

Sample은 Maturity/Grade/Health/측정값 등 object-level metadata revision을 가진다.

### Source asset identity

Preflight 단계의 논리 key:

```text
source_asset_key = farm_id + ':' + capture_session_id + ':' + normalized(Original_No)
```

실제 Working Asset Store의 최종 identity는 content SHA-256이다.

```text
working_asset_id = content_sha256
```

즉 source filename/Original_No는 provenance와 matching key이고, content hash가 저장 파일 identity다.

## 3. `Original_No` 중복의 의미

같은 `Original_No`가 여러 sample row에 존재하는 것 자체는 오류가 아니다.

```text
same Original_No + compatible context + one physical file
→ SHARED_SOURCE_ASSET
→ 정상 many-to-one relation
```

공유 asset의 실제 파일은 content-addressed object store에 한 번만 저장하고, 여러 sample manifest row가 같은 `source_asset_key`와 `content_sha256`을 참조한다.

## 4. Context conflict

같은 `Original_No`를 공유하는 row들 사이에서 다음 source context가 서로 다르면 자동 동일 asset으로 확정하지 않는다.

- `Date`
- `Zone`
- `DataType`

```text
same Original_No
+ Date/Zone/DataType conflict
→ SOURCE_ASSET_CONTEXT_CONFLICT
→ PREFLIGHT_BLOCKED
→ operator review
```

`Group_ID` 차이만으로는 blocking하지 않는다. 한 이미지 안에 여러 분석 object가 존재할 수 있기 때문이다.

`Class` 차이도 단독 blocking 조건으로 사용하지 않는다. 실제 asset 자체와 object-level task label을 분리한다.

## 5. Count 검증

파일 수를 Sheet row 수와 직접 비교하지 않는다.

잘못된 방식:

```text
sheet_rows == source_files
```

올바른 방식:

```text
expected_source_assets = distinct valid Original_No groups
expected_source_assets == source_files
```

따라서 2개 sample row가 같은 원본 사진 1장을 공유하면:

```text
sheet_rows = 2
expected_source_assets = 1
source_files = 1
→ count 정상
```

## 6. Rename / Final_Name 의미

`Final_Name`은 sample-level canonical logical name이다. source asset의 유일한 physical filename일 필요는 없다.

```text
Content Object Store
└─ <sha256>.jpg      # physical object 1개

Session Logical View
├─ Final_Name_A.jpg  ─┐
└─ Final_Name_B.jpg  ─┴→ same content object
```

filesystem이 hardlink를 지원하면 logical view는 hardlink를 우선하고, 불가능할 때만 copy fallback을 사용한다. 원본 source file은 변경하지 않는다.

## 7. Preflight 상태

### 정상/정보 상태

- `ONE_TO_ONE_SOURCE_ASSET`
- `SHARED_SOURCE_ASSET`
- `ORIGINAL_NO_EXACT`
- `NATURAL_ORDER_FALLBACK`

### Blocking

- `SOURCE_ASSET_CONTEXT_CONFLICT`
- `AMBIGUOUS_SOURCE_FILE`
- `SOURCE_ASSET_COUNT_MISMATCH`
- `MISSING_SOURCE_FILE`
- `EXTRA_SOURCE_FILE`
- `EMPTY_FINAL_NAME`
- `DUPLICATE_FINAL_NAME`
- `UNMATCHED_ORIGINAL_NO`
- `UNSUPPORTED_EXTENSION`
- `INVALID_METADATA`

`DUPLICATE_ORIGINAL_NO`는 더 이상 단독 blocking error가 아니다.

## 8. Manifest contract

Sample manifest는 최소 다음을 가진다.

```text
farm_id
capture_session_id
sample_id
source_asset_key
source_original_no
source_file
target_final_name
asset_relation
match_strategy
validation_status
content_sha256
working_object_path
working_session_path
```

여러 sample row가 같은 asset을 공유하면 `source_asset_key`, `source_file`, `content_sha256`, `working_object_path`가 동일할 수 있다.

## 9. Training Snapshot

Training Snapshot은 sample row와 physical asset을 별도로 고정한다.

```text
Sample Revision Set
+ Sample → Asset Relation
+ Asset SHA-256 Set
→ Normalize / Dedup / Split
→ Immutable Training Snapshot
```

동일 asset을 참조하는 여러 sample이 split leakage를 만들 수 있으므로 **같은 content SHA-256을 가진 sample은 cross-split 금지**한다. 기존 Group_ID atomicity보다 asset-sharing 제약이 더 강하면 asset hash 기준을 우선한다.

## 10. 실제 field source audit에서 확인된 이유

2026-09-10 live Sheet audit에서 다음 구조가 확인되었다.

- ID가 있는 active metadata row: 110
- STR row: 98
- LEF row: 12
- 동일 `Original_No`가 여러 sample row에 사용되는 shared-source 사례 존재
- 동일 `Original_No`가 서로 다른 Zone에서 재사용된 context-conflict 사례도 존재
- Drive의 M/C/U 촬영 source folder는 현재 비어 있어 physical file 검증은 아직 수행할 수 없음

raw row/개인 field asset은 Git에 기록하지 않고 aggregate finding만 유지한다.

## 11. 구현 규칙

- Preflight는 sample count가 아니라 distinct source asset count를 기준으로 한다.
- 같은 source asset의 SHA-256은 한 번만 계산/저장해 재사용할 수 있다.
- context conflict는 자동 교정하지 않는다.
- duplicate/typo 가능성이 있는 `Original_No`를 임의 수정하지 않는다.
- operator가 source metadata를 수정하면 Incremental Revision Ledger가 변경 이력을 남긴다.
- 원본 Sheet/사진/영상은 read-only다.
