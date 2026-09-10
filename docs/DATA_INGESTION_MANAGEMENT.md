# Nongtori Data Ingestion & Management Design

Status: **CANONICAL / DESIGN_FROZEN_CANDIDATE**

이 문서는 농토리의 현장 원본 데이터 수집·정리·파일명 정규화·검증·snapshot 생성 기능의 소유 경계와 운영 UX를 정의한다.

## 1. 핵심 원칙

현장 원본은 모델링 편의를 위해 직접 수정하지 않는다.

```text
Canonical Source
(Google Sheet / Raw Photo / Raw Video / Sensor Export)
        ↓ READ ONLY
Source Export / Working Copy
        ↓
Preflight Audit
        ↓
Rename / Metadata Match Manifest
        ↓
Validated Working Assets
        ↓
Normalize
→ Dedup
→ Split
→ Immutable Training Snapshot
```

금지:
- Google Sheet 원본 자동 수정
- 원본 사진/영상 기본값 직접 rename
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
│  ├─ 사진 데이터
│  ├─ 영상 데이터
│  ├─ 센서 / 환경 데이터
│  ├─ 파일-메타데이터 검증
│  ├─ 오류 / 누락
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
source_snapshot_id: ...
source_type: GOOGLE_SHEET_SNAPSHOT | CSV_SNAPSHOT | PHOTO_FOLDER | VIDEO_FOLDER
created_at: ...
```

UI에서 내부 ID를 사람이 직접 입력하게 하지 않는다. 농가/수집일/구역/데이터 타입 선택을 통해 시스템이 적절한 session을 생성·선택한다.

## 4. Google Sheet 원본 보호

`딸기_프로젝트`는 working canonical source이며 read-only input으로 사용한다.

파이프라인 실행 시 원본을 직접 수정하지 않고 export snapshot을 생성한다.

예:

```text
FIELD_SOURCE_20260910_v001.xlsx
FIELD_SOURCE_20260915_v002.xlsx
```

source snapshot은 immutable 취급한다. 동일 이름/버전을 overwrite하지 않는다.

실제 private source 파일은 Git에 커밋하지 않는다. Git에는 다음만 기록할 수 있다.
- source snapshot ID
- checksum/hash
- row/file count
- schema/label policy version
- aggregate audit result

## 5. 사진 파일명 정리

Google Sheet의 `Final_Name`을 canonical target filename으로 사용할 수 있다.

기본 매칭 우선순위:

```text
1. Original_No exact match
2. EXIF/capture timestamp match (source가 신뢰 가능할 때)
3. Natural order fallback
```

`ORDER_ONLY`는 명시적 fallback이며 기본값이 아니다.

### Preflight Audit
rename 전에 전체 세션을 검증한다.

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
- `INVALID_METADATA`

하나라도 blocking error가 있으면 rename job 전체를 중단한다.

## 6. Rename Manifest

rename은 즉시 파일을 변경하지 않고 먼저 manifest를 생성한다.

```text
source_file
source_original_no
target_final_name
farm_id
capture_session_id
match_strategy
validation_status
rename_status
```

사용자는 `변경 예정 보기`에서 rename 결과를 먼저 확인할 수 있어야 한다.

## 7. Working Copy 정책

기본 동작은 원본 파일을 보존하고 Working Copy를 생성한 뒤 복사본에 rename을 적용한다.

```text
Raw Source Folder (immutable)
        ↓ COPY
Working Session Folder
        ↓ rename
Validated Working Assets
```

`원본 직접 rename`은 향후 필요 시 별도 privileged option으로 둘 수 있으나 기본값은 OFF다.

## 8. 안전한 Rename 알고리즘

이름 충돌 방지를 위해 2단계 rename을 사용한다.

```text
source.jpg
→ .__nongtori_tmp__<id>.jpg
→ canonical_final_name.jpg
```

rename 전후 manifest를 남겨 rollback 가능성을 확보한다.

작업 중 실패하면 완료/미완료 파일을 구분해 `PARTIAL_FAILURE`로 기록하고 자동으로 정상 완료처럼 처리하지 않는다.

## 9. 농가별 카테고리 UX

데이터 관리센터 첫 화면은 농가 단위 집계를 제공한다.

예:

```text
M 농가
├─ 2026-01-05 / 숲촌4동-4-A / RGB / 검증 완료
├─ 2026-01-06 / 숲촌4동-4-B / 파일명 검증 필요
└─ 2026-01-07 / 두양4동-5-A / 사진 2개 누락
```

농가 내부에서 다시 수집 세션 단위로 drill-down한다.

수집 세션 상세에는 최소 다음을 표시한다.
- Sheet 대상 수
- 발견 asset 수
- Original_No exact match 수
- fallback match 수
- missing/extra/unmatched 수
- duplicate target name 수
- validation 상태
- Working Copy 생성 여부
- rename 실행/완료 상태

## 10. Repository / Domain 책임

권장 Domain:
- `DataIngestionJob`
- `CaptureSession`
- `SourceSnapshot`
- `AssetMatch`
- `RenameManifest`
- `IngestionAuditResult`

권장 Repository:
- `CaptureSessionRepository`
- `SourceSnapshotRepository`
- `IngestionJobRepository`
- `AssetManifestRepository`

권장 Infrastructure/Adapter:
- `FieldSpreadsheetAdapter`
- `FileSystemAssetAdapter`
- `ExifMetadataAdapter`
- `SourceExportAdapter`
- `NotificationAdapter`

규칙:
- Controller가 파일시스템/Repository 직접 조작 금지
- Service가 rename 순서/검증 orchestration 담당
- Repository는 파일명 정책이나 match 판단 금지
- Match/Rename 정책은 Domain/Strategy로 분리

## 11. 알림 정책

자동 rename job에서 blocking mismatch가 발생하면 파일을 변경하지 않고 운영자에게 알린다.

알림 예:

```text
M 농가 / 2026-01-05 / 숲촌4동-4-A
Sheet 대상 48 / 사진 49
추가 파일 1건, Final_Name 누락 1건
파일명 변경은 실행되지 않았습니다.
```

알림은 `NotificationAdapter`를 통해 UI notification/outbox 등으로 전달하고, 파일 처리 계층이 직접 사용자 메시지를 발송하지 않는다.

## 12. Training Pipeline 연결

```text
Source Snapshot
→ Ingestion Audit
→ Validated Working Assets
→ Field / External Normalize
→ Dedup
→ Split
→ Immutable Training Snapshot
```

`Validated Working Assets`를 통과하지 않은 세션은 자동으로 training snapshot에 포함하지 않는다.

## 13. 향후 확장

- S3/R2/object storage ingestion
- 모바일 촬영 즉시 canonical naming
- EXIF+영상 timestamp 기반 자동 세션 분류
- checksum 기반 원본/working copy integrity validation
- 대용량 resumable ingestion
- 농가별 데이터 품질 KPI

이 확장은 현재 `farm_id + capture_session_id + source_snapshot_id` 경계를 유지하는 범위에서 추가한다.
