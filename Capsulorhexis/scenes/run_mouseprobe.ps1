$ErrorActionPreference="Stop"
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
& "$env:SOFA_ROOT\bin\runSofa.exe" -l SofaPython3 -g imgui -a (Join-Path $PSScriptRoot "mouse_probe.py")
