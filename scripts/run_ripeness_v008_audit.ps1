param(
    [string]$Python = "python",
    [Parameter(Mandatory=$true)][string]$ResNetCheckpoint,
    [Parameter(Mandatory=$true)][string]$EfficientNetCheckpoint,
    [string]$Workdir = "artifacts/ripeness-v008-error-audit"
)

$ErrorActionPreference = "Stop"
Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V008 - RESIDUAL ERROR CEILING AUDIT"
Write-Host "============================================================"
& $Python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m ml.ripeness_baseline.audit_errors_v008 `
  --workdir $Workdir `
  --resnet-checkpoint $ResNetCheckpoint `
  --efficientnet-checkpoint $EfficientNetCheckpoint
exit $LASTEXITCODE
