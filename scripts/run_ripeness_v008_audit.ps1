param(
    [string]$Python = "python",
    [int]$Seed = 20260912,
    [string]$ConfirmationRoot = "artifacts/ripeness-v007-efficientnet-b0-confirmation-local-gpu",
    [string]$ResNetCheckpoint = "",
    [string]$EfficientNetCheckpoint = "",
    [string]$Workdir = "artifacts/ripeness-v008-error-audit"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ResNetCheckpoint)) {
    $ResNetCheckpoint = Join-Path $ConfirmationRoot "seed-$Seed/LR-5e-05-seed-$Seed/checkpoints/best.pt"
}
if ([string]::IsNullOrWhiteSpace($EfficientNetCheckpoint)) {
    $EfficientNetCheckpoint = Join-Path $ConfirmationRoot "seed-$Seed/EFFICIENTNET-B0-LR-5e-05-seed-$Seed/checkpoints/best.pt"
}

Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V008 - RESIDUAL ERROR CEILING AUDIT"
Write-Host "============================================================"
Write-Host "Audit seed          : $Seed"
Write-Host "ResNet checkpoint   : $ResNetCheckpoint"
Write-Host "EfficientNet ckpt   : $EfficientNetCheckpoint"

if (-not (Test-Path $ResNetCheckpoint)) {
    throw "ResNet checkpoint not found: $ResNetCheckpoint"
}
if (-not (Test-Path $EfficientNetCheckpoint)) {
    throw "EfficientNet checkpoint not found: $EfficientNetCheckpoint"
}

& $Python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m ml.ripeness_baseline.audit_errors_v008 `
  --workdir $Workdir `
  --seed $Seed `
  --resnet-checkpoint $ResNetCheckpoint `
  --efficientnet-checkpoint $EfficientNetCheckpoint
exit $LASTEXITCODE
