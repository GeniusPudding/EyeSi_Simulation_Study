$ErrorActionPreference="Stop"
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
& py -3.12 (Join-Path $PSScriptRoot "generate_cap.py")   # (re)generate lens.obj
& "$env:SOFA_ROOT\bin\runSofa.exe" -l SofaPython3 -g imgui -a (Join-Path $PSScriptRoot "cap_tear_geo.py")
