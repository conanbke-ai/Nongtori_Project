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
