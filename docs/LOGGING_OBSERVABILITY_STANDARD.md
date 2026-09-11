# Nongtori Logging & Observability Standard

Status: **CANONICAL / REQUIRED**

이 문서는 Nongtori의 데이터 수집, 정규화, 모델 학습, 평가, API/배치 작업에서 반드시 남겨야 하는 로그와 진행 상태를 정의한다. 새 구현은 특별한 사유가 없는 한 이 기준을 따른다.

## 1. 목적

테스트/운영 중 다음 질문에 로그만 보고 답할 수 있어야 한다.

- 지금 어떤 단계인가?
- 전체 중 몇 % 진행됐는가?
- 입력/처리/성공/실패 건수는 몇 개인가?
- 현재 metric과 이전 best는 얼마인가?
- checkpoint가 생성/갱신되었는가?
- retry가 발생했는가?
- 어디서 왜 실패했는가?
- 동일 설정으로 재현 가능한가?

## 2. 출력 형식

모든 장기 실행 작업은 두 형식을 동시에 유지한다.

1. 사람에게 읽기 쉬운 console log
2. 기계가 읽을 수 있는 JSONL structured event log

공통 필드:

```text
timestamp
level
run_id
component
phase
event
message
progress_current
progress_total
progress_pct
elapsed_sec
```

필요 시:

```text
experiment_id
snapshot_id
epoch
batch
metric_name
metric_value
learning_rate
checkpoint_path
checkpoint_sha256
retry_count
error_type
stack_trace
```

## 3. Log level

- `DEBUG`: 상세 진단, batch/sample 수준. 기본 CI artifact에는 남기되 console 과다 출력은 제한 가능
- `INFO`: 단계 시작/완료, 진행률, epoch summary, checkpoint 생성, 최종 metric
- `WARNING`: retry, low-confidence, recoverable data anomaly, early-stopping counter 증가
- `ERROR`: row/file 실패, metric 계산 실패, checkpoint 저장 실패 등 작업 일부 실패
- `CRITICAL`: snapshot contract 위반, 학습 불가, 결과 artifact 생성 실패 등 run 실패

## 4. Progress logging

장기 작업은 진행률을 반드시 남긴다.

### 데이터 작업

```text
[INGEST] 340/1477 (23.0%) success=338 failed=2 elapsed=...
```

최소 기준:
- 시작 시 total 기록
- 5% 단위 또는 50건 단위 중 더 자주 발생하는 시점에 progress 출력
- 마지막에 100% summary

### 모델 학습

각 epoch에서 최소 다음을 기록한다.

```text
Epoch 03/30
train_loss
valid_loss
macro_f1
accuracy
ordinal_mae
weighted_kappa
learning_rate
best_metric
best_epoch
early_stopping_counter
checkpoint_saved
elapsed_sec
```

가능하면 batch 단위 진행률도 10% 간격으로 INFO 또는 DEBUG로 기록한다.

## 5. Metric policy

문제 유형에 맞는 metric만 기록한다.

### Classification / Ordinal classification

- train loss
- validation loss
- accuracy
- Macro F1
- per-class Precision / Recall / F1
- confusion matrix
- ordinal task이면 Ordinal MAE / Weighted Kappa

`R²`는 일반 분류 모델에 사용하지 않는다.

### Regression

- train/valid loss
- R²
- MAE
- RMSE
- 필요 시 sMAPE / WAPE

### Detection

- train losses (box/class/dfl 등 모델 제공 항목)
- mAP50
- mAP50-95
- Precision
- Recall

### Tracking

- HOTA / IDF1
- ID Switch
- Fragmentation
- Unique Fruit Count Error
- FPS / VRAM

## 6. Checkpoint logging

checkpoint 생성/갱신은 반드시 event로 남긴다.

```text
event=CHECKPOINT_SAVED
path=...
metric=valid_macro_f1
metric_value=...
epoch=...
sha256=...
```

실패 시 `ERROR` 후 stack trace를 남기며 checkpoint가 없는데 run을 성공 처리하지 않는다.

최종 결과에는 최소:

- best checkpoint 존재 여부
- checkpoint SHA-256
- best epoch
- best validation metric
- config/seed/snapshot id

를 기록한다.

## 7. Error / retry logging

외부 API/파일 다운로드 등 retry가 있는 모든 경로는:

```text
attempt
max_attempts
error_type
error_message
backoff_sec
```

를 WARNING으로 기록한다.

최종 실패 시 ERROR/CRITICAL과 전체 stack trace를 저장한다.

`except Exception: pass` 금지.

## 8. Run artifacts

장기 실행 작업의 artifact 기본 구조:

```text
run/
├─ run.log
├─ events.jsonl
├─ metrics.json
├─ config.json
├─ error.log              # 오류가 있을 때
├─ checkpoints/
│  └─ best.pt
└─ summaries/
   └─ run_summary.json
```

Git에는 대형 모델/원본 데이터를 올리지 않고 Actions/외부 artifact store에 보관한다.

## 9. Run summary

성공/실패 관계없이 `run_summary.json`을 최대한 생성한다.

최소 필드:

```text
run_id
status
started_at
finished_at
duration_sec
input_count
processed_count
success_count
failed_count
warning_count
error_count
best_checkpoint
best_metric
final_metrics
```

## 10. CI / 테스트 acceptance

장기 작업은 stdout만 보고 성공 처리하지 않는다.

- process exit code 정상
- structured events artifact 존재
- summary 존재
- required metrics 존재
- checkpoint required task면 checkpoint 존재 + hash 기록
- error_count 검토
- snapshot/config/seed 기록

을 함께 확인한다.

## 11. 적용 범위

즉시 적용:
- Ripeness Baseline V001 및 이후 모든 모델 학습
- Dataset Registry / Downloader / Audit / Normalize / Dedup / Split
- Field ingestion / rename / materialization
- price forecast/backtest
- pest/detection/tracking 실험

UI/API runtime logging은 개인정보와 원본 이미지 payload를 로그에 직접 남기지 않는 것을 원칙으로 한다.

## 12. 개인정보 및 데이터 안전

로그에 다음을 직접 기록하지 않는다.

- 원본 이미지 binary
- 인증 토큰/API key
- 개인정보
- 필요 이상의 전체 Sheet row payload

대신 source key/hash/error code/count 중심으로 기록한다.
