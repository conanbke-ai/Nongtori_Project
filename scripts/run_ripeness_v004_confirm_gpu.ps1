param(
    [string]$Python = "",
    [string]$WorkDir = "artifacts/ripeness-v004-cosine-confirmation-local-gpu",
    [int]$Epochs = 15,
    [double]$EtaMin = 0.000005
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V004 - 3-SEED GPU CONFIRMATION"
Write-Host "============================================================"

if ([string]::IsNullOrWhiteSpace($Python) -and -not [string]::IsNullOrWhiteSpace($env:CONDA_PREFIX)) {
    $candidate = Join-Path $env:CONDA_PREFIX "python.exe"
    if (Test-Path $candidate) { $Python = $candidate }
}
if ([string]::IsNullOrWhiteSpace($Python)) { $Python = "python" }

Write-Host "Python : $Python"
& $Python -c "import sys,torch; print('Executable:',sys.executable); print('PyTorch:',torch.__version__); print('CUDA available:',torch.cuda.is_available()); print('CUDA:',torch.version.cuda); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); sys.exit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) { throw "CUDA GPU is required for canonical confirmation experiments." }

& $Python -u -m ml.ripeness_baseline.confirm_scheduler_v004 `
    --workdir $WorkDir `
    --epochs $Epochs `
    --eta-min $EtaMin

if ($LASTEXITCODE -ne 0) {
    throw "RIPENESS V004 confirmation failed. Check $WorkDir/run.log and error.log."
}

Write-Host ""
Write-Host "Confirmation completed."
Write-Host "Result  : $WorkDir/confirmation.json"
Write-Host "Summary : $WorkDir/summaries/run_summary.json"
Write-Host "Events  : $WorkDir/events.jsonl"
Write-Host "Run log : $WorkDir/run.log"
