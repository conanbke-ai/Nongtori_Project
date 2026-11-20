# Nongtori ML Execution Environment Policy

Status: **CANONICAL / REQUIRED**

## 1. Principle

Nongtori의 정식 ML/DL 성능 실험은 **개발자의 로컬 CUDA GPU 환경**을 canonical execution environment로 사용한다.

GitHub Actions의 일반 CPU runner는 모델 성능 측정, Optuna, backbone 비교, multi-seed confirmation 용도로 사용하지 않는다.

```text
Local CUDA GPU
→ real training
→ validation experiment
→ Optuna
→ backbone comparison
→ multi-seed confirmation
→ candidate checkpoint

GitHub Actions CPU
→ import / syntax
→ model construction
→ freeze / unfreeze contract
→ synthetic forward/backward
→ checkpoint creation
→ logging / summary contract
→ data/snapshot unit contract
```

## 2. Why

CPU와 GPU는 동일 알고리즘의 기능 검증에는 사용할 수 있지만, Nongtori의 실제 개발 환경에서 반복적인 장시간 CPU 학습은 비용 대비 가치가 낮다.

정식 성능 실험은 실제 사용할 GPU 환경에서 수행하고 실행 환경 자체를 evidence에 기록한다.

## 3. Canonical experiment requirements

정식 실험 artifact에는 최소 다음을 기록한다.

- run id
- git commit SHA
- experiment id
- snapshot id / assignment checksum
- seed
- Python version
- PyTorch version
- CUDA version
- GPU name
- GPU count
- batch size
- AMP enabled/disabled
- model/backbone
- optimizer / LR / scheduler
- epoch별 train/valid metric
- peak VRAM when available
- elapsed time
- best checkpoint SHA-256
- final decision

GPU가 없으면 canonical training command는 실패해야 한다. CPU fallback으로 조용히 정식 실험을 계속하지 않는다.

## 4. GitHub Actions policy

CI는 빠른 smoke test만 수행한다.

Smoke test는:

- 외부 학습 데이터 전체 다운로드 금지
- pretrained weight 다운로드 불필요
- synthetic tensor 또는 tiny fixture 사용
- 실제 모델 graph 생성
- forward/backward 최소 1회
- freeze/unfreeze contract 검증
- checkpoint 생성 검증
- structured logging 검증
- 목표 실행시간 15분 이내

Smoke metric은 모델 성능 evidence로 기록하지 않는다.

## 5. Local GPU execution

Windows PowerShell canonical launcher:

```powershell
.\scripts\run_ripeness_v003_gpu.ps1
```

실행 전 CUDA가 실제 PyTorch에서 인식되는지 검사한다. CUDA가 없으면 즉시 중단한다.

직접 Python으로 실행할 수도 있다.

```powershell
python -u -m ml.ripeness_baseline.screen_staged_v003 `
  --workdir artifacts/ripeness-v003-staged-local-gpu `
  --epochs 15 `
  --warmup-epochs 2 `
  --seed 20260910
```

단, canonical launcher를 사용하는 것을 우선한다.

## 6. Evidence handling

로컬 GPU 실행 결과 중 모든 raw run은 로컬 artifact에 남긴다.

모델 개선 문서에는 `MODEL_EXPERIMENT_EVIDENCE_POLICY.md`에 따라 실제 의사결정을 바꾸는 유의미한 결과만 기록한다.

Git에는 대형 crop/image/checkpoint 자체를 기본 커밋하지 않는다. 대신 필요 시 다음 경량 evidence를 관리한다.

- config
- result summary
- metric table
- checkpoint SHA-256
- environment metadata
- experiment decision

## 7. Test-set rule

실행 환경이 GPU로 바뀌어도 test-set 정책은 변하지 않는다.

```text
validation experiment
→ candidate decision
→ confirmation
→ configuration freeze
→ final test
```

GPU가 빠르다는 이유로 frozen test를 반복 조회하면서 tuning하지 않는다.

---
## 8. Single-GPU training throughput optimization protocol (2026-11-20)

Status: **BENCHMARK PLANNED / GPU NOT RUN**. Goal: reduce historical half-day training cycle (user recollection; no confirmed run ID) **without** losing acceptance-quality model metrics or compromising the immutable dataset boundary. Target is local NVIDIA RTX 4060, exact RAM/VRAM/disk/driver and local environment to be read from runtime, not assumed.

### Verified code audit (GitHub main)

- `ml/detector_baseline/mite_yolo11_reference_v001.py`: YOLO11-Large `yolo11l.pt`, 100 epochs, image size 1024, `--workers` default 4, CUDA required, wall-clock `elapsed_sec`; confirm actual Ultralytics defaults for AMP/cache/batch at runtime.
- `ml/detector_baseline/mite_field_v001.py`: PyTorch DataLoader `num_workers=args.workers` default 4, CUDA `pin_memory=True`, epoch `elapsed_sec`.
- `ml/ripeness_baseline/train_v001.py`: DataLoader batch 32, workers 2, `pin_memory=False`, epoch duration recorded; do not change without verifying current canonical ripeness experiment and cache semantics.
- `ml/ripeness_baseline/cache_io.py`: existing crop cache validation/reuse; do not recreate verified caches unnecessarily.
- These are **repository code facts**, not proof that a specific historic run used them.

### Profiling before optimization

1. Locate historical half-day run logs/config, identify whether it included data acquisition, decode/crops, cache creation, training, validation or download; if unavailable, document baseline as `UNKNOWN`, run a new measured A0.
2. Freeze source/manifest/snapshot IDs, assignment checksum, checkpoint/architecture, seed, epochs, image size, LR/optimizer, batch, software versions, hardware and thermal/power settings. Ensure GPU is actually used; don't silently fall back to CPU.
3. Instrument separate durations: acquisition/audit (if applicable), cache preparation, DataLoader wait and transforms, H2D copies, forward/backward/optimizer, validation, checkpoint I/O, full elapsed. GPU async timings require `torch.cuda.synchronize()` or CUDA events; don't synchronize each batch in final optimized run.
4. Log GPU utilization, VRAM peak, CPU, RAM, disk throughput, images/sec and epoch time; warmup and cold-cache vs warm-cache results must be labeled separately.
5. Conduct short-screening benchmarks on a **fixed subset with no leakage** and enough warmup; then run complete training for final check. Keep results in local raw artifacts and only meaningful decisions in model log.

### Controlled A0–A5 matrix

| ID | Tested variable | Hold fixed / risk |
|---|---|---|
| A0 | unchanged canonical implementation | true baseline, wall-clock + model performance |
| A1 | DataLoader workers 0 / 2 / 4 / 8 (only feasible values) | RAM and Windows spawn overhead; more workers need not be faster |
| A2 | cache off / disk / RAM *where supported* | disk/RAM budget, snapshot identity, cold/warm cache distinction |
| A3 | AMP off / on (only if supported and stable) | validate loss, metrics, numeric stability and actual dtype; default may already be on |
| A4 | batch and CPU prefetch/persistent_workers/pinned memory where supported | batch impacts optimization; isolate and monitor VRAM/OOM, LR and metrics |
| A5 | winning combination + full same-budget training | multiple seeds/confirmation if performance comparison materially changes |

Optional `torch.compile`: consider only when long enough training amortizes compilation and runtime/framework compatible; record compile warmup separately. Early stopping is **algorithmic budget reduction**, not faster per-epoch throughput; report separately, never mislabel as hardware speedup. Distributed Data Parallel needs multiple CUDA GPUs and is **out of scope** with one RTX 4060. SageMaker HyperPod is study/reference only unless separately authorized and budgeted.

### Acceptance / reporting

- Primary: total full-run wall-clock, epoch seconds, images/sec, relative speed-up and percent time saved.
- Safety: same data split, unchanged test lock, validation mAP/Recall or ripeness Macro F1/Ordinal MAE, GPU peak VRAM and reproducibility.
- Formula: `time_saved_pct = 100 * (baseline_seconds - candidate_seconds) / baseline_seconds`; `speedup_x = baseline_seconds / candidate_seconds`.
- Screen target ≥30% time reduction, stretch ≥50%; these are **candidate goals, not achieved results**.
- Keep an explicit `NOT_RUN` marker until actual local GPU execution evidence is present. No paid GPU/cloud or production-worker activation without approval.
