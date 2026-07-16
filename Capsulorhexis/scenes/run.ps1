<#
    Launch the capsulorhexis scene in the runSofa GUI (which frames the disc and
    supports Shift+drag interaction). Tearing should be validated here, not
    headless (a manual animate loop mis-propagates topology changes).

    Usage:  ./scenes/run.ps1
#>
[CmdletBinding()]
param([string]$Scene = "capsule_ccc.py")

$ErrorActionPreference = "Stop"
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
$ScenesDir = $PSScriptRoot
$PluginRoot = Split-Path -Parent $ScenesDir
$BuildDir = Join-Path $PluginRoot "build"
$dll = Join-Path $BuildDir "Capsulorhexis.dll"
if (-not (Test-Path $dll)) { throw "Capsulorhexis.dll not found. Run scripts/setup.ps1 first." }

# Generate the mesh if missing.
if (-not (Test-Path (Join-Path $ScenesDir "capsule.obj"))) {
    & py -3.12 (Join-Path $ScenesDir "generate_capsule.py")
}

$runSofa = Join-Path $env:SOFA_ROOT "bin\runSofa.exe"
if (-not (Test-Path $runSofa)) { throw "runSofa not found at $runSofa" }

# Make the plugin discoverable by runSofa's PluginManager (its dependents live in
# SOFA/bin, already on runSofa's load path).
$env:SOFA_PLUGIN_PATH = $BuildDir

Write-Host "Launching runSofa on $Scene ..." -ForegroundColor Green
# -a starts the animation immediately (otherwise runSofa opens paused and mouse
# interaction is ignored until you press Play).
& $runSofa -l SofaPython3 -g imgui -a (Join-Path $ScenesDir $Scene)
