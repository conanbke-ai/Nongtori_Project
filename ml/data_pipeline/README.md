# Nongtori Data Pipeline

재현 가능한 외부/현장 데이터 수집부터 training snapshot까지 담당한다.

```text
Dataset Registry → Download / Extract → Audit → Normalize → Exact Dedup → Atomic Split → Training Snapshot
```

## Label contract

현장 Google Sheet는 read-only source다. Normalize 단계에서만 파생 필드를 생성한다.

- `Grade=SP/HI/MD/JM` → `observed_harvest=true`
- `Grade=NA` → `observed_harvest=false`
- `Health=MAL` → `Grade=JM` 계약 검사
- `Maturity=3` → `TURNING_LATE`; 수확 여부는 Grade로 결정
- 외부 `OVERRIPE` → `Maturity=4`, `Grade=JM`, `grade_reason=OVERRIPE`
- 외부 source에는 실제 수확 행동이 없으면 `observed_harvest`를 생성하지 않는다.
- `JM → JAM`, `Maturity=4 → JM`, `Grade=JM → MAL` 역규칙은 금지한다.

정책 기준은 `docs/LABEL_MAPPING_POLICY.md`다.

## Commands

```bash
python -m ml.data_pipeline.cli normalize-field --input field.csv --output work/normalized-field.csv
python -m ml.data_pipeline.cli normalize-external --input external.csv --mapping ml/data_pipeline/mappings/strawberry_ds_v1.json --output work/normalized-external.csv
python -m ml.data_pipeline.cli dedup --input work/normalized.csv --output work/dedup.csv
python -m ml.data_pipeline.cli split --input work/dedup.csv --output work/split.csv --seed nongtori-v1
python -m ml.data_pipeline.cli training-snapshot --snapshot-id STRAWBERRY_RIPENESS_v001 --normalized work/normalized.csv --dedup work/dedup.csv --split work/split.csv --snapshot-root data/snapshots --label-mapping-version MAP-FIELD-001-v1 --source-id DATA-FIELD-001
```

Exact duplicate는 `content_sha256`가 있을 때만 제거한다. 해시가 없는 행을 추정 중복으로 버리지 않는다. Split은 `atomic_group` 단위로 결정한다. field image는 `Group_ID`, video는 capture/session, external은 source sequence/group을 사용한다. 동일 atomic group과 동일 SHA-256은 active split을 넘을 수 없다.

현재 외부 mapping은 `strawberry_ds_v1.json`, `agml_growth_v1.json`이다. AgML `turning red`는 decimal-stage audit 전까지 `UNMAPPED` 및 training exclusion 상태다.
