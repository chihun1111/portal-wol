Param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")
$webDir = Join-Path $root "web"
$staticDir = Join-Path $root "app/static"
$outDir = Join-Path $webDir "out"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error "npm is required to build the frontend."
}

Push-Location $webDir
if (-not $SkipInstall -or -not (Test-Path (Join-Path $webDir "node_modules"))) {
  npm install
}
if (-not $env:NEXT_PUBLIC_API_BASE) {
  $env:NEXT_PUBLIC_API_BASE = ""
}
npm run build
Pop-Location

if (-not (Test-Path $outDir)) {
  Write-Error "Build output not found at $outDir"
}

if (Test-Path $staticDir) {
  Remove-Item $staticDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $staticDir | Out-Null
Copy-Item (Join-Path $outDir '*') $staticDir -Recurse

if (Test-Path (Join-Path $staticDir "index.html")) {
  Write-Host "Frontend assets copied to app/static."
} else {
  Write-Warning "index.html missing from build output."
}
