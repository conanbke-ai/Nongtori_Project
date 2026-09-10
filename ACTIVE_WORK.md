# Nongtori Active Work Registry

이 파일은 여러 대화창/세션에서 같은 기능을 중복 구현하지 않기 위한 현재 작업 기준표다. 새 작업 전에 반드시 open PR/branch와 함께 확인한다.

## 현재 Budget

- Branch budget: `main` 포함 최대 5개
- Active workstream: 최대 3개
- Validation branch: 최대 1개
- 현재 remote branch: `main` = 1/5
- GitHub `delete_branch_on_merge=true` 적용 확인: 병합된 feature branch는 자동 삭제

| Workstream | Canonical branch / PR | 상태 | Owner / Lease 경로 | 시작/최근 활동 | Acceptance Criteria / 다음 단계 |
|---|---|---|---|---|---|
| TORI UI System v1 | `main` / merged PR #1 | MERGED_BASELINE | owner 없음 | 2026-09-08 | 기존 foundation 유지 |
| Nongtori Design Freeze v1 | `main` | DESIGN_FROZEN / DATA_WIP | owner 없음 / canonical docs | 2026-09-10 | label semantics, farm/session 경계, incremental ingestion/revision semantics 유지 |
| Canonical application source 편입 | `main` / merged PR #2 | MERGED_BASELINE | owner 없음 | 2026-09-10 | 운영센터 baseline 유지 |
| AI Data Pipeline v1 Core | `main` / merged PR #3 | MERGED_BASELINE | owner 없음 | 2026-09-10 | Dataset Registry/provider/audit baseline 유지 |
| Normalize / Dedup / Split / Training Snapshot v1 | `main` / merged PR #4 | MERGED_BASELINE | owner 없음 | 2026-09-10 | label normalize, exact dedup, atomic split, immutable snapshot 유지 |
| Farm-scoped Data Ingestion Design | `main` / merged PR #5 + follow-up docs | DESIGN_FROZEN | owner 없음 | 2026-09-10 | baseline 1회 + incremental scan/change detection + append-only revision + content-hash asset reuse |
| Incremental Ingestion + Field Task Audit v1 | `main` / merged PR #6 | MERGED_BASELINE | owner 없음 | 2026-09-10 | `NEW/UPDATED/REMOVED/UNCHANGED`, revision ledger, field-level diff, STR/LEF task 분리 완료 |
| Farm-scoped Rename Manifest + Working Asset Reuse v1 | `main` / merged PR #7 | MERGED_BASELINE | owner 없음 | 2026-09-10 | Original_No exact, blocking preflight, SHA-256 object store reuse, Final_Name working view, rollback manifest 완료 |
| External Annotation Audit v1 | `main` / merged PR #8 | MERGED_BASELINE | owner 없음 | 2026-09-10 | Strawberry-DS YOLO audit, KGCV LabelMe/decimal-stage audit, source-specific CLI/tests/CI 완료. `turning red` threshold는 실제 분포+field calibration 전까지 발명 금지. |

## 다음 canonical workstream

```text
실제 DATA-RIP-001 / DATA-RIP-002 raw annotation audit 실행
→ AgML turning-red empirical calibration
→ Actual Field + External Normalized Manifest
→ Actual Dedup / Split
→ Training Snapshot v001
→ Baseline Model
→ Optuna
```

### 현재 구현 완료 핵심

- 원본 Google Sheet/사진/영상 read-only
- incremental ingestion + revision ledger
- STR/LEF task eligibility 분리
- farm/capture-session rename preflight + content-addressed working asset reuse
- Strawberry-DS 6-class YOLO annotation audit parser
- KGCV 7 main stage + diameter/length/decimal_stage annotation audit parser
- KGCV decimal_stage를 global maturity가 아닌 main-stage 내부 진행도(DS-0..DS-10 equivalent)로 취급
- `turning red` Maturity 2/3 threshold는 관측 분포와 field calibration 전까지 `DO_NOT_INVENT_THRESHOLD`
- CI는 `tests/test_*.py` 전체 discovery

### 다음 실행 핵심

1. 실제 추출된 DATA-RIP-001 annotation에 `audit-strawberry-ds` 실행
2. 실제 추출된 DATA-RIP-002 tagged/random JSON에 `audit-kgcv` 실행
3. class/decimal-stage distribution 검토 후 turning-red threshold calibration
4. Field + External actual normalized manifest 생성
5. actual dedup/split manifest 및 Training Snapshot v001 생성

새 AI/data 구현은 `docs/DESIGN_FREEZE_V1.md`, `docs/LABEL_MAPPING_POLICY.md`, `docs/DATA_INGESTION_MANAGEMENT.md`, `docs/MULTI_FARM_DATA_MODEL.md`를 기준으로 한다.

## Branch hygiene

- feature branch는 실제 독립 구현 workstream에만 생성
- PR merge 후 GitHub 자동 삭제
- 기준 상태 보존은 backup branch보다 tag 우선

## 데이터 안전

Google Sheets/외부 원본/현장 사진·영상은 read-only source다. 기존 revision과 asset은 덮어쓰지 않는다. 학습/평가는 latest eligible ACTIVE revision을 선택해 immutable Training Snapshot manifest로 고정한다.
