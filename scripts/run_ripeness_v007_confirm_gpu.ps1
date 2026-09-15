param(
    [string]$Python = "",
    [string]$WorkDir = "artifacts/ripeness-v007-efficientnet-b0-confirmation-local-gpu",
    [int]$Epochs = 15
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V007 - MULTI-SEED ARCHITECTURE CONFIRMATION"
Write-Host "============================================================"

if ([string]::IsNullOrWhiteSpace($Python)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CONDA_PREFIX)) {
        $candidate = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path $candidate) { $Python = $candidate }
    }
}
if ([string]::IsNullOrWhiteSpace($Python)) { $Python = "python" }

Write-Host "Python : $Python"
& $Python -c "import sys,torch; print('Executable:',sys.executable); print('PyTorch:',torch.__version__); print('CUDA available:',torch.cuda.is_available()); print('CUDA:',torch.version.cuda); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); sys.exit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) {
    throw "CUDA GPU is required for canonical model confirmation."
}

& $Python -u -m ml.ripeness_baseline.confirm_backbone_v007 `
    --workdir $WorkDir `
    --epochs $Epochs

if ($LASTEXITCODE -ne 0) {
    throw "RIPENESS V007 confirmation failed. Check $WorkDir/run.log and error.log."
}

Write-Host ""
Write-Host "Confirmation completed."
Write-Host "Result  : $WorkDir/confirmation.json"
Write-Host "Summary : $WorkDir/summaries/run_summary.json"
Write-Host "Events  : $WorkDir/events.jsonl"
Write-Host "Run log : $WorkDir/run.log"
