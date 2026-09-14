param(
    [string]$Python = "",
    [string]$WorkDir = "artifacts/ripeness-v006-ordinal-loss-local-gpu",
    [int]$Epochs = 15,
    [double]$OrdinalLambda = 0.20
)
$ErrorActionPreference = "Stop"
Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V006 - ORDINAL LOSS GPU SCREENING"
Write-Host "============================================================"
if ([string]::IsNullOrWhiteSpace($Python) -and -not [string]::IsNullOrWhiteSpace($env:CONDA_PREFIX)) {
    $candidate = Join-Path $env:CONDA_PREFIX "python.exe"
    if (Test-Path $candidate) { $Python = $candidate }
}
if ([string]::IsNullOrWhiteSpace($Python)) { $Python = "python" }
Write-Host "Python : $Python"
& $Python -c "import sys,torch; print('Executable:',sys.executable); print('PyTorch:',torch.__version__); print('CUDA available:',torch.cuda.is_available()); print('CUDA:',torch.version.cuda); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); sys.exit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) { throw "CUDA GPU is required for canonical model experiments." }
& $Python -u -m ml.ripeness_baseline.screen_ordinal_loss_v006 --workdir $WorkDir --epochs $Epochs --ordinal-lambda $OrdinalLambda
if ($LASTEXITCODE -ne 0) { throw "RIPENESS V006 failed. Check $WorkDir/run.log and error.log." }
Write-Host "Experiment completed."
Write-Host "Comparison : $WorkDir/comparison.json"
Write-Host "Summary    : $WorkDir/summaries/run_summary.json"
