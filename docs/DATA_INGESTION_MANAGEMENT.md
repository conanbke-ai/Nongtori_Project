# Nongtori Data Ingestion & Management Design

Status: **CANONICAL / DESIGN_FROZEN_CANDIDATE**

이 문서는 농토리의 현장 원본 데이터 수집·정리·파일명 정규화·검증·증분 반영·snapshot 생성 기능의 소유 경계와 운영 UX를 정의한다.

## 1. 핵심 원칙

현장 원본은 모델링 편의를 위해 직접 수정하지 않는다. 초기 1회는 전체 기준선(baseline)을 만들고, 이후 ingestion은 전체 source를 다시 읽어 변경 여부를 비교하되 **신규·변경분만 저장**한다.

```text
Canonical Source
(Google Sheet / Raw Photo / Raw Video / Sensor Export)
        ↓ READ ONLY
Source Scan / Change Detection
        ↓
NEW / UPDATED / REMOVED / UNCHANGED
        ↓
Revision Ledger + Working Asset Store
        ↓
Preflight Audit / Rename Manifest
        ↓
Validated Working Assets
        ↓
Normalize
→ Dedup
→ Split
→ Immutable Training Snapshot Manifest
```

금지:
- Google Sheet 원본 자동 수정
- 원본 사진/영상 기본값 직접 rename
- 매 실행마다 전체 source/asset을 무조건 재복사
- 기존 revision 덮어쓰기
- source에서 사라진 데이터를 즉시 물리 삭제
- 검증 전 순서 기반 일괄 rename
- 다른 농가/수집 세션 파일 혼합
- mismatch가 있는데 부분 rename 강행

## 2. 사용자 영역 분리

### Farmer / Worker UI
농장주·작업자는 결과 중심 화면만 사용한다.

노출 예:
- 오늘 수집된 이미지/영상 건수
- 분석 완료/대기/오류 건수
- 수확·병해충·생육 결과
- 재촬영/확인 필요 알림

기본적으로 노출하지 않음:
- Original_No
- 파일 일괄 rename
- revision ledger
- field-level diff
- Dedup manifest
- Dataset snapshot hash
- split manifest
- 개발용 source path

### Operator / Data Manager UI
데이터 정리·수집 품질 관리는 운영자 전용 `데이터 관리센터`에서 수행한다.

권장 메뉴:

```text
운영자
├─ 농가 관리
├─ 데이터 관리센터
│  ├─ 수집 현황
│  ├─ 신규 / 변경 / 삭제 / 오류
│  ├─ 사진 데이터
│  ├─ 영상 데이터
│  ├─ 센서 / 환경 데이터
│  ├─ 파일-메타데이터 검증
│  ├─ Revision 이력
│  └─ Dataset / Snapshot
├─ AI 모델 관리
└─ 시스템 관리
```

## 3. 데이터 소유 경계

데이터 관리의 최소 경계는 `farm_id`와 `capture_session_id`다.

```text
Farm
└─ Capture Session
   ├─ Date / Time
   ├─ House / Bed / Zone
   ├─ Crop / Variety
   ├─ DataType
   └─ Assets
      ├─ RGB Photo
      ├─ Thermal Photo
      ├─ Video
      └─ Sensor/Metadata
```

`Farm`만으로 수천 개 파일을 한 묶음으로 관리하지 않는다.

모든 ingestion job은 최소 다음 provenance를 갖는다.

```yaml
farm_id: ...
capture_session_id: ...
source_scan_id: ...
source_type: GOOGLE_SHEET | CSV | PHOTO_FOLDER | VIDEO_FOLDER
created_at: ...
```

UI에서 내부 ID를 사람이 직접 입력하게 하지 않는다. 농가/수집일/구역/데이터 타입 선택을 통해 시스템이 적절한 session을 생성·선택한다.

## 4. 초기 Baseline + Incremental Ingestion

### 최초 ingestion

최초 1회는 source 전체를 스캔해 기준선을 만든다.

```text
Full Source Scan
→ Baseline Revision Ledger
→ Baseline Working Asset Store
```

### 이후 ingestion

이후 실행에서는 source 전체를 다시 읽어 현재 상태를 비교하지만, 저장/복사는 변경분만 수행한다.

행/메타데이터 상태:

```text
NEW        source_key 없음
UNCHANGED  source_key 있음 + row_hash 동일
UPDATED    source_key 있음 + row_hash 변경
REMOVED    이전에는 존재했으나 현재 source에서 사라짐
INVALID    계약 위반/파싱 불가
```

처리:
- `NEW`: 새 revision 추가
- `UNCHANGED`: 아무 저장 작업 없음
- `UPDATED`: 기존 revision을 `SUPERSEDED`, 새 revision을 `ACTIVE`로 추가
- `REMOVED`: 기존 데이터를 삭제하지 않고 `REMOVED_FROM_SOURCE` 상태 기록
- `INVALID`: 원본을 보존하고 오류 상태/사유 기록

## 5. Source Key / Row Hash / Field Diff

행 변경 감지에는 안정적인 source key와 row hash를 사용한다.

권장 field source key:

```text
source_key = farm_id + ':' + ID
```

`ID`의 유일성 범위가 capture session으로 제한되는 source는 다음처럼 확장한다.

```text
source_key = farm_id + ':' + capture_session_id + ':' + ID
```

`row_hash`는 학습/운영 의미가 있는 정규화 전 source field를 canonical 순서로 직렬화해 SHA-256으로 계산한다. 표시용 수식/휘발성 값은 별도 정책으로 제외할 수 있다.

`UPDATED`에서는 hash만 저장하지 않고 field-level diff도 남긴다.

예:

```json
{
  "source_key": "M:0042",
  "from_revision": 1,
  "to_revision": 2,
  "changed_fields": {
    "Grade": {"old": "NA", "new": "SP"},
    "Weight_g": {"old": "", "new": "24.2"}
  }
}
```

## 6. Revision Ledger

메타데이터는 append-only revision으로 관리한다.

권장 필드:

```text
source_key
revision
row_hash
source_status
changed_fields_json
source_scan_id
imported_at
supersedes_revision
```

상태 예:
- `ACTIVE`
- `SUPERSEDED`
- `REMOVED_FROM_SOURCE`
- `INVALID`

기존 revision을 update-in-place 하지 않는다.

## 7. Asset Store / 사진·영상 변경 감지

실제 파일은 content hash(SHA-256)를 기준으로 재사용한다.

```text
새 content hash
→ Working Asset Store에 1회 저장

기존 content hash
→ 재복사하지 않고 기존 asset 참조
```

같은 `Original_No`/source filename인데 content hash가 달라지면 자동 덮어쓰기하지 않는다.

```text
SAME_SOURCE_NAME_CONTENT_CHANGED
→ 기존 asset revision SUPERSEDED
→ 새 asset revision ACTIVE
→ operator audit 기록
```

Asset 권장 필드:

```text
asset_key
source_name
content_sha256
revision
status
raw_source_path
working_asset_ref
source_scan_id
```

## 8. Google Sheet 원본 보호

`딸기_프로젝트`는 working canonical source이며 read-only input으로 사용한다.

매 실행마다 전체 `.xlsx` 복사본을 보관할 필요는 없다. 대신 source scan provenance와 revision ledger를 남긴다.

필요한 경우에만 checkpoint 성격의 immutable full export를 만들 수 있다.

예:

```text
FIELD_SOURCE_BASELINE_20260910_v001.xlsx
FIELD_SOURCE_CHECKPOINT_20261001_v002.xlsx
```

일반적인 일일/수시 ingestion은 full export 복제 대신 row hash/change detection으로 처리한다.

실제 private source/export 파일은 Git에 커밋하지 않는다. Git에는 다음만 기록할 수 있다.
- source scan/checkpoint ID
- checksum/hash
- row/file count
- schema/label policy version
- aggregate audit result

## 9. 사진 파일명 정리

Google Sheet의 `Final_Name`을 canonical logical filename으로 사용할 수 있다.

기본 매칭 우선순위:

```text
1. Original_No exact match
2. EXIF/capture timestamp match (source가 신뢰 가능할 때)
3. Natural order fallback
```

`ORDER_ONLY`는 명시적 fallback이며 기본값이 아니다.

### Preflight Audit
rename 전에 해당 세션 변경 대상 전체를 검증한다.

상태 코드 예:
- `READY_TO_RENAME`
- `FILE_COUNT_MISMATCH`
- `SHEET_ROW_COUNT_MISMATCH`
- `MISSING_SOURCE_FILE`
- `EXTRA_SOURCE_FILE`
- `EMPTY_FINAL_NAME`
- `DUPLICATE_FINAL_NAME`
- `DUPLICATE_ORIGINAL_NO`
- `UNMATCHED_ORIGINAL_NO`
- `UNSUPPORTED_EXTENSION`
- `TARGET_FILE_ALREADY_EXISTS`
- `SAME_SOURCE_NAME_CONTENT_CHANGED`
- `INVALID_METADATA`

하나라도 blocking error가 있으면 해당 ingestion job의 rename 단계를 중단한다.

## 10. Rename Manifest

rename은 즉시 파일을 변경하지 않고 먼저 manifest를 생성한다.

```text
source_file
source_original_no
target_final_name
farm_id
capture_session_id
asset_revision
match_strategy
validation_status
rename_status
```

사용자는 `변경 예정 보기`에서 rename 결과를 먼저 확인할 수 있어야 한다.

기존에 이미 validated working asset으로 저장된 동일 content hash는 다시 복사/rename하지 않고 기존 참조를 재사용한다.

## 11. Working Asset 정책

기존의 “매 실행 전체 Working Copy 생성”을 기본 정책으로 사용하지 않는다.

권장 구조:

```text
Raw Source (read-only)
        ↓ incremental scanner
Content-addressed / revisioned Working Asset Store
        ↓ logical canonical filename / manifest
Validated Working Assets
```

즉:
- 최초 baseline 시 필요한 asset만 저장
- 이후 신규/변경 asset만 추가
- unchanged asset은 기존 working asset 참조 재사용
- superseded asset은 보존하되 최신 학습 대상에서는 제외

`원본 직접 rename`은 기본값 OFF다.

## 12. 안전한 Rename 알고리즘

실제 filesystem rename이 필요한 경우 이름 충돌 방지를 위해 2단계 rename을 사용한다.

```text
source.jpg
→ .__nongtori_tmp__<id>.jpg
→ canonical_final_name.jpg
```

rename 전후 manifest를 남겨 rollback 가능성을 확보한다.

작업 중 실패하면 완료/미완료 파일을 구분해 `PARTIAL_FAILURE`로 기록하고 자동으로 정상 완료처럼 처리하지 않는다.

## 13. 농가별 카테고리 UX

데이터 관리센터 첫 화면은 농가 단위 집계를 제공한다.

예:

```text
M 농가
├─ 신규 20
├─ 변경 4
├─ 삭제 감지 1
├─ 오류 2
└─ Unchanged 3,214
```

농가 내부에서 capture session 단위로 drill-down한다.

수집 세션 상세에는 최소 다음을 표시한다.
- source row/asset 수
- NEW / UPDATED / REMOVED / UNCHANGED 수
- Original_No exact match 수
- fallback match 수
- missing/extra/unmatched 수
- duplicate target name 수
- changed field 요약
- validation 상태
- 새로 저장한 working asset 수
- 기존 asset 재사용 수
- rename 실행/완료 상태

## 14. Repository / Domain 책임

권장 Domain:
- `DataIngestionJob`
- `CaptureSession`
- `SourceScan`
- `SourceRevision`
- `AssetRevision`
- `ChangeSet`
- `AssetMatch`
- `RenameManifest`
- `IngestionAuditResult`

권장 Repository:
- `CaptureSessionRepository`
- `SourceRevisionRepository`
- `AssetRevisionRepository`
- `IngestionJobRepository`
- `AssetManifestRepository`

권장 Infrastructure/Adapter:
- `FieldSpreadsheetAdapter`
- `FileSystemAssetAdapter`
- `ExifMetadataAdapter`
- `SourceScannerAdapter`
- `ContentHashAdapter`
- `NotificationAdapter`

규칙:
- Controller가 파일시스템/Repository 직접 조작 금지
- Service가 scan → compare → revision → preflight → manifest → post-audit orchestration 담당
- Repository는 파일명 정책이나 match/change 판단 금지
- Change Detection / Match / Rename 정책은 Domain/Strategy로 분리

## 15. 알림 정책

자동 ingestion/rename job에서 blocking mismatch가 발생하면 원본을 변경하지 않고 운영자에게 알린다.

알림 예:

```text
M 농가 / 2026-01-05 / 숲촌4동-4-A
신규 20 / 변경 4 / 삭제 감지 1 / 오류 1
Original_No 불일치 1건
해당 파일명 변경은 실행되지 않았습니다.
```

알림은 `NotificationAdapter`를 통해 UI notification/outbox 등으로 전달하고, 파일 처리 계층이 직접 사용자 메시지를 발송하지 않는다.

## 16. Training Snapshot 연결

Training Snapshot은 source/asset 전체를 매번 물리 복제하지 않는다.

```text
Revision Ledger + Working Asset Store
→ latest eligible ACTIVE revisions 선택
→ Normalize
→ Dedup
→ Split
→ Immutable Training Snapshot Manifest
```

Snapshot에는 최소 다음을 고정한다.

```yaml
snapshot_id: ...
source_scan_ids: []
source_revision_set_hash: ...
asset_hashes: []
normalized_manifest_hash: ...
split_manifest_hash: ...
created_at: ...
```

같은 content hash asset은 여러 Training Snapshot에서 안전하게 재사용할 수 있다. Snapshot의 불변성은 물리 파일 복제 횟수가 아니라 **참조한 revision/hash 집합의 불변성**으로 보장한다.

## 17. 삭제/정정 정책

source에서 행/파일이 사라져도 기존 revision/asset을 즉시 삭제하지 않는다.

```text
REMOVED_FROM_SOURCE
```

로 기록하고 이후 snapshot 기본 대상에서는 제외한다.

정정된 데이터는 기존 revision을 `SUPERSEDED`, 새 revision을 `ACTIVE`로 두어 과거 실험 재현성을 보장한다.

## 18. 향후 확장

- S3/R2/object storage content-addressed ingestion
- 모바일 촬영 즉시 canonical naming
- EXIF+영상 timestamp 기반 자동 세션 분류
- 대용량 resumable ingestion
- 농가별 데이터 품질 KPI
- checkpoint/full export 보존 주기 정책

이 확장은 현재 `farm_id + capture_session_id + source_key + revision + content_sha256` 경계를 유지하는 범위에서 추가한다.
