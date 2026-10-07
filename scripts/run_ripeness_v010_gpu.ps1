param(
    [string]$Python = "python",
    [int]$Epochs = 15,
    [int]$Seed = 20260910,
    [string]$Workdir = "artifacts/ripeness-v010-convnext-tiny-local-gpu"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V010 - CONVNEXT-TINY SCREENING"
Write-Host "============================================================"
Write-Host "Python  : $Python"
Write-Host "Seed    : $Seed"
Write-Host "Epochs  : $Epochs"
Write-Host "Workdir : $Workdir"
Write-Host "Field/Drive data: NOT USED"

& $Python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m ml.ripeness_baseline.screen_backbone_v010 `
  --workdir $Workdir `
  --epochs $Epochs `
  --seed $Seed

exit $LASTEXITCODE
