param(
  [string]$DistDir = "deploy\dist\FaceCheckin",
  [string]$MsiPath = "deploy\installer\FaceCheckin-0.1.0.msi"
)

$ErrorActionPreference = "Stop"

function Size-MB($path) {
  if (-not (Test-Path $path)) { return "missing" }
  $item = Get-Item $path
  if ($item.PSIsContainer) {
    $bytes = (Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  } else {
    $bytes = $item.Length
  }
  return ("{0:N1} MB" -f ($bytes / 1MB))
}

$checks = @(
  @{ Name = "EXE"; Path = Join-Path $DistDir "FaceCheckin.exe" },
  @{ Name = "Bundled static"; Path = Join-Path $DistDir "_internal\backend\static" },
  @{ Name = "Model det_10g"; Path = Join-Path $DistDir "_internal\models\insightface\buffalo_l\det_10g.onnx" },
  @{ Name = "Model w600k_r50"; Path = Join-Path $DistDir "_internal\models\insightface\buffalo_l\w600k_r50.onnx" },
  @{ Name = "MSI"; Path = $MsiPath }
)

Write-Host "FaceCheckin package inspection"
Write-Host "Dist: $DistDir"
Write-Host ""

foreach ($check in $checks) {
  $exists = Test-Path $check.Path
  $status = if ($exists) { "OK" } else { "MISSING" }
  $size = if ($exists) { Size-MB $check.Path } else { "-" }
  Write-Host ("{0,-18} {1,-8} {2,10}  {3}" -f $check.Name, $status, $size, $check.Path)
}

Write-Host ""
Write-Host ("Dist size: {0}" -f (Size-MB $DistDir))

$runtimeItems = @("attendance.db", "attendance.db-wal", "attendance.db-shm", "data", "cache", "received", "processed", "models")
$presentRuntime = @()
foreach ($name in $runtimeItems) {
  $path = Join-Path $DistDir $name
  if (Test-Path $path) { $presentRuntime += $name }
}

if ($presentRuntime.Count) {
  Write-Host ""
  Write-Host "WARNING: runtime data exists in dist and may be bundled into MSI:" -ForegroundColor Yellow
  foreach ($name in $presentRuntime) { Write-Host "  - $name" -ForegroundColor Yellow }
  Write-Host "Clean these after smoke tests unless this is intentional seed data." -ForegroundColor Yellow
} else {
  Write-Host ""
  Write-Host "Runtime data check: clean for MSI source." -ForegroundColor Green
}
