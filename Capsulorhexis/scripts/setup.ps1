<#
    Capsulorhexis plugin - one-command setup (clone -> setup -> build).

    Usage:   ./scripts/setup.ps1

    Idempotent. Fetches the one third-party dependency that the SOFA binary SDK
    does not ship (header-only Eigen) into tools/, then configures and builds the
    plugin and runs the unit test. Safe to re-run.

    Prerequisites the script checks for (and reports if missing):
      - a SOFA binary SDK  (set $env:SOFA_ROOT, default C:\SOFA\SOFA_v25.12.00_Win64)
      - CMake, Ninja, Visual Studio 2022 Build Tools (MSVC x64)
      - curl + tar (bundled with Windows 10/11)
#>
[CmdletBinding()]
param(
    [string]$EigenVersion = "3.4.0"
)

$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $PluginRoot "tools"

Write-Host "=== Capsulorhexis setup ===" -ForegroundColor Green

# --- prerequisite checks ---------------------------------------------------
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
$missing = @()
if (-not (Test-Path $env:SOFA_ROOT)) { $missing += "SOFA SDK (set `$env:SOFA_ROOT; got '$($env:SOFA_ROOT)')" }
if (-not (Get-Command cmake -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\CMake\bin\cmake.exe")) { $missing += "CMake" }
if (-not (Test-Path "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")) { $missing += "Visual Studio 2022 (vswhere)" }
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { $missing += "curl" }
if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) { $missing += "tar" }
if ($missing.Count) {
    Write-Host "Missing prerequisites:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    throw "Install the above, then re-run setup."
}
Write-Host "Prerequisites OK. SOFA_ROOT = $($env:SOFA_ROOT)" -ForegroundColor Cyan

# --- fetch Eigen (idempotent) ----------------------------------------------
New-Item -ItemType Directory -Force $ToolsDir | Out-Null
$eigenDir = Join-Path $ToolsDir "eigen-$EigenVersion"
if (Test-Path (Join-Path $eigenDir "Eigen\Dense")) {
    Write-Host "Eigen $EigenVersion already present -> $eigenDir" -ForegroundColor Cyan
} else {
    $tarball = Join-Path $ToolsDir "eigen-$EigenVersion.tar.gz"
    $url = "https://gitlab.com/libeigen/eigen/-/archive/$EigenVersion/eigen-$EigenVersion.tar.gz"
    Write-Host "Downloading Eigen $EigenVersion ..." -ForegroundColor Cyan
    & curl.exe -fsSL -o $tarball $url
    if ($LASTEXITCODE -ne 0) { throw "Eigen download failed from $url" }
    & tar.exe -xzf $tarball -C $ToolsDir
    if ($LASTEXITCODE -ne 0) { throw "Eigen extract failed" }
    Remove-Item $tarball -Force
    if (-not (Test-Path (Join-Path $eigenDir "Eigen\Dense"))) { throw "Eigen not where expected: $eigenDir" }
    Write-Host "Eigen ready -> $eigenDir" -ForegroundColor Green
}

# --- build + test ----------------------------------------------------------
Write-Host "`nBuilding plugin ..." -ForegroundColor Green
& (Join-Path $PSScriptRoot "build.ps1") -Clean
if ($LASTEXITCODE -ne 0) { throw "Build failed." }

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host "Plugin DLL:  $PluginRoot\build\Capsulorhexis.dll"
Write-Host "Load test :  py -3.12 scripts\load_test.py"
