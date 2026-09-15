param(
    [string]$Python = "python",
    [string]$AuditDir = "artifacts/ripeness-v008-error-audit",
    [string]$OutputDir = "artifacts/ripeness-v008-review-gallery"
)

$ErrorActionPreference = "Stop"
Write-Host "============================================================"
Write-Host " NONGTORI - RIPENESS V008 - HARD EXAMPLE REVIEW GALLERY"
Write-Host "============================================================"

& $Python -m ml.ripeness_baseline.build_review_gallery_v008 `
  --audit-dir $AuditDir `
  --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$gallery = Join-Path $OutputDir "review_gallery.html"
Write-Host ""
Write-Host "Review gallery ready: $gallery"
Write-Host "Opening in default browser..."
Start-Process $gallery
