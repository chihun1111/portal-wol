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
try {
  if (-not $SkipInstall -or -not (Test-Path (Join-Path $webDir "node_modules"))) {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
      throw "Frontend dependency installation failed (exit code $LASTEXITCODE)."
    }
  }
  if (-not $env:NEXT_PUBLIC_API_BASE) {
    $env:NEXT_PUBLIC_API_BASE = ""
  }
  npm run build
  if ($LASTEXITCODE -ne 0) {
    throw "Frontend build failed (exit code $LASTEXITCODE)."
  }
} finally {
  Pop-Location
}

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
