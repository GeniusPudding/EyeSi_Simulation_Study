<#
    Launch the paper/gel tearing demo in the runSofa GUI (which frames the sheet
    and enables Shift+drag mouse tearing). This demo uses ONLY stock SOFA + the
    Tearing plugin -- it does NOT need Capsulorhexis.dll.

    Usage:  ./scenes/run_paper.ps1
#>
[CmdletBinding()]
param([string]$Scene = "paper_gel_tear.py")

$ErrorActionPreference = "Stop"
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
$ScenesDir = $PSScriptRoot

$runSofa = Join-Path $env:SOFA_ROOT "bin\runSofa.exe"
if (-not (Test-Path $runSofa)) { throw "runSofa not found at $runSofa" }

Write-Host "Launching runSofa on $Scene ..." -ForegroundColor Green
# -a starts animation immediately (otherwise runSofa opens paused and ignores the
# mouse until you press Play).
& $runSofa -l SofaPython3 -g imgui -a (Join-Path $ScenesDir $Scene)
