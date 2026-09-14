param(
    [string]$Python = "",
    [string]$WorkDir = "artifacts/ripeness-v005-label-smoothing-local-gpu",
    [int]$Epochs = 15,
    [int]$Seed = 20260910
)
$ErrorActionPreference="Stop"
Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V005 - LABEL SMOOTHING GPU SCREENING"
Write-Host "============================================================"
if ([string]::IsNullOrWhiteSpace($Python) -and -not [string]::IsNullOrWhiteSpace($env:CONDA_PREFIX)) {
    $candidate=Join-Path $env:CONDA_PREFIX "python.exe"; if (Test-Path $candidate) {$Python=$candidate}
}
if ([string]::IsNullOrWhiteSpace($Python)) {$Python="python"}
Write-Host "Python : $Python"
& $Python -c "import sys,torch; print('Executable:',sys.executable); print('PyTorch:',torch.__version__); print('CUDA available:',torch.cuda.is_available()); print('CUDA:',torch.version.cuda); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); sys.exit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) {throw "CUDA GPU is required."}
& $Python -u -m ml.ripeness_baseline.screen_loss_v005 --workdir $WorkDir --epochs $Epochs --seed $Seed
if ($LASTEXITCODE -ne 0) {throw "V005 failed. Check $WorkDir/run.log and error.log."}
Write-Host "Experiment completed."
Write-Host "Comparison : $WorkDir/comparison.json"
Write-Host "Summary    : $WorkDir/summaries/run_summary.json"
