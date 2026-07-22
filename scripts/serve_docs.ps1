# Launch the local Markdown docs viewer (Windows convenience wrapper).
# Usage:  ./scripts/serve_docs.ps1  [-Port 8777] [-NoBrowser]
param(
    [int]$Port = 8777,
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue) }
if (-not $py) { Write-Error "Python not found on PATH. Install Python 3.9+ and retry."; exit 1 }

$args = @("$repo\scripts\serve_docs.py", "--port", $Port)
if ($NoBrowser) { $args += "--no-browser" }
& $py.Source @args
