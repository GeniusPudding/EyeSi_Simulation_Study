<#
    Launch the cap-on-lens capsulorhexis demo in the runSofa GUI. Stock SOFA only
    (no Capsulorhexis.dll). Regenerates the meshes first.

    DEFAULT is cap_tear.py -- the FREE, stress-driven tear: Shift+left-drag the flap and
    the crack follows YOUR pull (perpendicular-to-sigma1), no hardcoded circle. It prints
    [Tear] lines (NOT [Peel]/[ClothToPaper] -- those belong to the old scene).

    Old adhesion-peel scene (pre-slit stitch circle, no free tearing):
        ./scenes/run_cap.ps1 -Scene cap_membrane.py

    Usage:  ./scenes/run_cap.ps1
#>
[CmdletBinding()]
param([string]$Scene = "cap_tear.py")

$ErrorActionPreference = "Stop"
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
$ScenesDir = $PSScriptRoot

# ALWAYS regenerate. Only regenerating when cap.obj was missing meant that editing the
# geometry (C = flatness, CAP_ANGLE_DEG = coverage, A = size, TARGET_EDGE = resolution)
# silently did nothing, because the stale mesh was reused.
& py -3.12 (Join-Path $ScenesDir "generate_cap.py")

$runSofa = Join-Path $env:SOFA_ROOT "bin\runSofa.exe"
if (-not (Test-Path $runSofa)) { throw "runSofa not found at $runSofa" }

Write-Host "Launching runSofa on $Scene ..." -ForegroundColor Green
& $runSofa -l SofaPython3 -g imgui -a (Join-Path $ScenesDir $Scene)
