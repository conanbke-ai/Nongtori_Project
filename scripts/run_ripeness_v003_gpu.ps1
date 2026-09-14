param(
    [string]$Python = "",
    [string]$WorkDir = "artifacts/ripeness-v003-staged-local-gpu",
    [int]$Epochs = 15,
    [int]$WarmupEpochs = 2,
    [int]$Seed = 20260910
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host " NONGTORI · RIPENESS V003 · LOCAL GPU EXPERIMENT"
Write-Host "============================================================"

$currentEnv = $env:CONDA_DEFAULT_ENV
$condaPrefix = $env:CONDA_PREFIX

if ([string]::IsNullOrWhiteSpace($Python)) {
    if (-not [string]::IsNullOrWhiteSpace($condaPrefix)) {
        $candidate = Join-Path $condaPrefix "python.exe"
        if (Test-Path $candidate) {
            $Python = $candidate
        }
    }
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "python"
}

Write-Host "Conda env : $currentEnv"
Write-Host "Python    : $Python"

& $Python -c "import sys,torch; print('Executable:',sys.executable); print('PyTorch:',torch.__version__); print('CUDA available:',torch.cuda.is_available()); print('CUDA:',torch.version.cuda); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); sys.exit(0 if torch.cuda.is_available() else 2)"
if ($LASTEXITCODE -ne 0) {
    throw "CUDA GPU is required for canonical model experiments. Verify the active Conda environment and CUDA-enabled PyTorch."
}

& $Python -u -m ml.ripeness_baseline.screen_staged_v003 `
    --workdir $WorkDir `
    --epochs $Epochs `
    --warmup-epochs $WarmupEpochs `
    --seed $Seed

if ($LASTEXITCODE -ne 0) {
    throw "RIPENESS V003 GPU experiment failed. Check $WorkDir/run.log and error.log."
}

Write-Host ""
Write-Host "Experiment completed."
Write-Host "Comparison : $WorkDir/comparison.json"
Write-Host "Summary    : $WorkDir/summaries/run_summary.json"
Write-Host "Events     : $WorkDir/events.jsonl"
Write-Host "Run log    : $WorkDir/run.log"
