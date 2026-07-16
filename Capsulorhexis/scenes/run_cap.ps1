<#
    Launch the cap-on-lens capsulorhexis demo in the runSofa GUI. Stock SOFA only
    (no Capsulorhexis.dll). Regenerates the meshes first.

    DEFAULT is cap_membrane.py -- the membrane simply SITS on the oblate lens, held down
    by a breakable adhesion. NOTHING is clamped (FIX_OUTER_RIM=False), so you can
    Shift+left-drag the RIM, lift it and FOLD IT OVER. Pull gently and the adhesion
    holds; pull harder and that spot peels off. It prints [Peel]/[ClothToPaper] lines.

    Usage:  ./scenes/run_cap.ps1
#>
[CmdletBinding()]
param([string]$Scene = "cap_membrane.py")

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
