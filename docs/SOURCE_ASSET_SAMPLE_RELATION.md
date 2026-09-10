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

한 장의 사진에 여러 분석 대상이 존재할 수 있으므로 하나의 source asset이 여러 sample row에 참조되는 many-to-one 관계를 허용한다.

## 2. Farm Code와 Farm Scope

개별 source row의 canonical `Farm` code:

```text
M / C1 / C2 / U
```

운영자 조회·Drive 상위 분류·ingestion job의 `Farm Scope`:

```text
M  → {M}
C  → {C1, C2}
C1 → {C1}
C2 → {C2}
U  → {U}
```

따라서 `C`는 오류 코드가 아니라 C1/C2를 함께 다루기 위한 정상적인 group/scope selector다. 단, 개별 sample provenance와 revision key에는 실제 row의 `C1` 또는 `C2`를 보존한다.

Drive의 `응애피해농가(C)`는 이 `C` scope와 자연스럽게 연결할 수 있으며, 하위 실제 sample의 Farm identity를 `C`로 덮어쓰지 않는다.

## 3. 식별자 분리

```text
sample_id = Sheet.ID
source_key = actual_farm_code + ':' + sample_id
source_asset_key = actual_farm_code + ':' + capture_session_id + ':' + normalized(Original_No)
working_asset_id = content_sha256
```

Farm Scope는 조회/작업 선택자이고 physical/sample identity의 일부로 사용하지 않는다.

## 4. `Original_No` 중복의 의미

같은 `Original_No`가 여러 sample row에 존재하는 것 자체는 오류가 아니다.

```text
same Original_No + compatible context + one physical file
→ SHARED_SOURCE_ASSET
```

## 5. Context conflict

같은 `Original_No`를 공유하는 row들 사이에서 다음 source context가 다르면 자동 동일 asset으로 확정하지 않는다.

- actual `Farm` code
- `Date`
- `Zone`
- `DataType`

```text
same Original_No + context conflict
→ SOURCE_ASSET_CONTEXT_CONFLICT
→ PREFLIGHT_BLOCKED
```

특히 C scope로 C1/C2를 함께 읽을 때 동일 Original_No가 양 농가에서 재사용되면 별도 asset으로 식별되거나 operator review가 필요하며, 단순 병합하지 않는다.

## 6. Count 검증

파일 수를 Sheet row 수와 직접 비교하지 않는다.

```text
expected_source_assets = distinct valid source asset groups
expected_source_assets == source_files
```

## 7. Rename / Final_Name

`Final_Name`은 sample-level canonical logical name이다. physical object는 content-addressed store에 한 번 저장할 수 있다.

```text
Content Object Store
└─ <sha256>.jpg

Session Logical View
├─ Final_Name_A.jpg
└─ Final_Name_B.jpg → same content object 가능
```

원본 source file은 변경하지 않는다.

## 8. Preflight 상태

정상/정보:
- `ONE_TO_ONE_SOURCE_ASSET`
- `SHARED_SOURCE_ASSET`
- `ORIGINAL_NO_EXACT`
- `NATURAL_ORDER_FALLBACK`

Blocking:
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

## 9. Manifest contract

```text
farm_id                 # actual M/C1/C2/U
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

Preflight summary에는 별도로 `farm_scope`와 `resolved_farm_codes`를 기록한다.

## 10. Training Snapshot

```text
Sample Revision Set
+ Sample → Asset Relation
+ Asset SHA-256 Set
→ Normalize / Dedup / Split
→ Immutable Training Snapshot
```

같은 content SHA-256을 가진 sample은 cross-split 금지한다.

## 11. 실제 field source audit

2026-09-10 live Sheet audit 기준:
- canonical Farm code: `M / C1 / C2 / U`
- ID가 있는 active metadata row: 110
- STR 98 / LEF 12
- shared-source 사례 존재
- Original_No context-conflict 사례 존재
- Drive 상위 분류 `응애피해농가(C)`는 C1/C2를 묶는 C scope로 취급 가능
- 현재 physical 촬영 파일이 없어 file/hash 검증은 아직 수행할 수 없음

raw row/개인 field asset은 Git에 기록하지 않고 aggregate finding만 유지한다.

## 12. 구현 규칙

- `C` scope 선택은 C1/C2를 함께 조회한다.
- 실제 sample/asset manifest의 `farm_id`는 C1/C2 원본 값을 보존한다.
- Preflight는 sample count가 아니라 distinct source asset count 기준이다.
- 같은 asset SHA-256은 재사용한다.
- context conflict는 자동 교정하지 않는다.
- 원본 Sheet/사진/영상은 read-only다.
