<#
    Capsulorhexis plugin - configure & build against the local SOFA SDK.

    Usage:   ./scripts/build.ps1 [-Clean] [-TestOnly] [-Config Release]

    - Finds MSVC via vswhere and imports its environment (so cl/ninja work).
    - Points CMAKE_PREFIX_PATH at $env:SOFA_ROOT and every plugin's lib/cmake,
      so find_package(Sofa.*) / find_package(Tearing) resolve.
    - Builds into build/ with Ninja.

    Requires: CMake, Ninja, Visual Studio 2022 (Build Tools), a SOFA binary SDK.
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$TestOnly,
    [string]$Config = "Release"
)

$ErrorActionPreference = "Stop"
$PluginRoot = Split-Path -Parent $PSScriptRoot
$BuildDir = Join-Path $PluginRoot "build"

# --- SOFA_ROOT -------------------------------------------------------------
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
if (-not (Test-Path $env:SOFA_ROOT)) {
    throw "SOFA_ROOT '$($env:SOFA_ROOT)' not found. Set `$env:SOFA_ROOT to your SOFA install."
}
Write-Host "SOFA_ROOT = $($env:SOFA_ROOT)" -ForegroundColor Cyan

# --- locate CMake / Ninja --------------------------------------------------
$cmakeCmd = Get-Command cmake -ErrorAction SilentlyContinue
if ($cmakeCmd) { $cmake = $cmakeCmd.Source } else { $cmake = "C:\Program Files\CMake\bin\cmake.exe" }
if (-not (Test-Path $cmake)) { throw "cmake not found." }

# --- import MSVC environment via vswhere -----------------------------------
$vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { throw "vswhere not found; install Visual Studio 2022." }
$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw "No MSVC x64 toolset found via vswhere." }
$vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars64.bat"
Write-Host "MSVC = $vsPath" -ForegroundColor Cyan

# Import vcvars64 into this PowerShell session (run the .bat, capture env).
cmd /c "`"$vcvars`" >nul 2>&1 && set" | ForEach-Object {
    if ($_ -match "^([^=]+)=(.*)$") { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}

# --- CMAKE_PREFIX_PATH: SOFA + every bundled plugin's lib/cmake -------------
$prefix = @($env:SOFA_ROOT, (Join-Path $env:SOFA_ROOT "lib\cmake"))
$pluginsDir = Join-Path $env:SOFA_ROOT "plugins"
if (Test-Path $pluginsDir) {
    Get-ChildItem $pluginsDir -Directory | ForEach-Object {
        $lc = Join-Path $_.FullName "lib\cmake"
        if (Test-Path $lc) { $prefix += $lc }
    }
}
$env:CMAKE_PREFIX_PATH = ($prefix -join ";")

# --- Eigen3 (SOFA dependency, not shipped in the binary SDK) ----------------
# scripts/setup.ps1 fetches header-only Eigen into tools/eigen-*/ ; find it.
$eigenInc = $null
$eigenDir = Get-ChildItem (Join-Path $PluginRoot "tools") -Directory -Filter "eigen-*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($eigenDir -and (Test-Path (Join-Path $eigenDir.FullName "Eigen\Dense"))) {
    $eigenInc = $eigenDir.FullName
    Write-Host "Eigen3 = $eigenInc" -ForegroundColor Cyan
} else {
    Write-Host "Eigen not found under tools/. Run scripts/setup.ps1 first." -ForegroundColor Yellow
}

if ($Clean -and (Test-Path $BuildDir)) {
    Write-Host "Cleaning $BuildDir" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $BuildDir
}

# --- configure -------------------------------------------------------------
$cfgArgs = @(
    "-S", $PluginRoot, "-B", $BuildDir, "-G", "Ninja",
    "-DCMAKE_BUILD_TYPE=$Config",
    "-DCMAKE_PREFIX_PATH=$($env:CMAKE_PREFIX_PATH)"
)
if ($eigenInc) {
    $cfgArgs += "-DEIGEN3_INCLUDE_DIR=$eigenInc"
    $cfgArgs += "-DCMAKE_POLICY_DEFAULT_CMP0167=NEW"
}
& $cmake @cfgArgs
if ($LASTEXITCODE -ne 0) { throw "CMake configure failed." }

# --- build -----------------------------------------------------------------
if ($TestOnly) {
    & $cmake --build $BuildDir --target Capsulorhexis_criterion_test
} else {
    & $cmake --build $BuildDir
}
if ($LASTEXITCODE -ne 0) { throw "Build failed." }

Write-Host "`nBuild OK -> $BuildDir" -ForegroundColor Green

# --- run the standalone criterion test if it was built ---------------------
$testExe = Join-Path $BuildDir "Capsulorhexis_criterion_test.exe"
if (Test-Path $testExe) {
    Write-Host "`nRunning criterion unit test:" -ForegroundColor Cyan
    & $testExe
    if ($LASTEXITCODE -ne 0) { throw "Criterion test FAILED." }
}
