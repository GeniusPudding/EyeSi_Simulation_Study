<#
.SYNOPSIS
    Run the SofaCUDA raptor example on CPU vs GPU so you can see the speed
    difference yourself — either side-by-side in the GUI, or as a headless
    FPS benchmark.

.DESCRIPTION
    The raptor scene (~19,400 tetrahedra, co-rotational FEM, implicit Euler +
    CG) ships in two flavours that differ ONLY by the template:
        raptor-cpu.scn   -> template="Vec3d"      (runs on CPU)
        raptor-cuda.scn  -> template="CudaVec3f"   (runs on GPU via SofaCUDA)
    Same physics, same solver, same iteration count. Any FPS gap is pure
    CPU-vs-GPU compute.

.PARAMETER Mode
    gui   : launch both scenes in the GUI, animation auto-started, so you can
            watch the CPU one crawl next to the GPU one. (default)
    bench : run both headless (batch) for -Steps steps and print an FPS table.

.PARAMETER Steps
    Number of simulation steps for bench mode. Default 500.

.PARAMETER SofaRoot
    SOFA install root. Auto-detected; override if yours lives elsewhere.

.EXAMPLE
    ./compare_raptor.ps1                 # watch both live, side by side
    ./compare_raptor.ps1 -Mode bench     # print FPS table (CPU vs GPU, speedup)
#>
[CmdletBinding()]
param(
    [ValidateSet('gui', 'bench')]
    [string]$Mode = 'gui',
    [int]$Steps = 500,
    [string]$SofaRoot = 'C:\SOFA\SOFA_v25.12.00_Win64'
)

$ErrorActionPreference = 'Stop'

# --- resolve paths -------------------------------------------------------
$runSofa = Join-Path $SofaRoot 'bin\runSofa.exe'
if (-not (Test-Path $runSofa)) {
    # fall back to PATH
    $cmd = Get-Command runSofa -ErrorAction SilentlyContinue
    if ($cmd) { $runSofa = $cmd.Source }
    else { throw "runSofa.exe not found under $SofaRoot and not on PATH. Pass -SofaRoot <dir>." }
}

$exampleDir = Join-Path $SofaRoot 'plugins\SofaCUDA\share\sofa\examples\SofaCUDA'
$cpuScene = Join-Path $exampleDir 'raptor-cpu.scn'
$gpuScene = Join-Path $exampleDir 'raptor-cuda.scn'
foreach ($s in @($cpuScene, $gpuScene)) {
    if (-not (Test-Path $s)) { throw "Scene not found: $s" }
}

Write-Host "runSofa : $runSofa"
Write-Host "CPU     : $cpuScene"
Write-Host "GPU     : $gpuScene`n"

# --- gui mode ------------------------------------------------------------
if ($Mode -eq 'gui') {
    Write-Host "Launching both scenes in the GUI (animation auto-started)."
    Write-Host "The CPU window will visibly lag; the GPU one runs smooth."
    Write-Host "Drag the two windows apart to compare. Close either to stop.`n"
    # -a starts the animation immediately so you don't have to hit play.
    Start-Process -FilePath $runSofa -ArgumentList @('-a', "`"$cpuScene`"")
    Start-Process -FilePath $runSofa -ArgumentList @('-a', "`"$gpuScene`"")
    Write-Host "Both windows launched."
    return
}

# --- bench mode ----------------------------------------------------------
function Measure-Scene {
    param([string]$Label, [string]$Scene)
    Write-Host "Running $Label ($Steps steps)..." -NoNewline
    # runSofa writes INFO/ERROR lines to stderr; in PS 5.1 invoking a native exe
    # that writes stderr can raise a terminating NativeCommandError. Start-Process
    # with redirected streams sidesteps PowerShell's error-stream handling entirely.
    $outFile = [System.IO.Path]::GetTempFileName()
    $errFile = [System.IO.Path]::GetTempFileName()
    $p = Start-Process -FilePath $runSofa `
        -ArgumentList @('-g', 'batch', '-n', "$Steps", "`"$Scene`"") `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    $raw = (Get-Content $outFile -Raw -ErrorAction SilentlyContinue) + "`n" +
           (Get-Content $errFile -Raw -ErrorAction SilentlyContinue)
    Remove-Item $outFile, $errFile -ErrorAction SilentlyContinue
    # BatchGUI prints: "N iterations done in T s ( F FPS)."
    $m = [regex]::Match($raw, 'iterations done in\s+([\d.]+)\s+s\s+\(\s+([\d.]+)\s+FPS')
    if (-not $m.Success) {
        Write-Host " FAILED to parse FPS."
        Write-Host $raw
        return $null
    }
    $sec = [double]$m.Groups[1].Value
    $fps = [double]$m.Groups[2].Value
    Write-Host (" {0:N2}s -> {1:N1} FPS" -f $sec, $fps)
    [pscustomobject]@{ Label = $Label; Seconds = $sec; FPS = $fps }
}

$cpu = Measure-Scene -Label 'CPU (Vec3d)'      -Scene $cpuScene
$gpu = Measure-Scene -Label 'GPU (CudaVec3f)'  -Scene $gpuScene

if ($cpu -and $gpu) {
    $speedup = $gpu.FPS / $cpu.FPS
    Write-Host "`n============ raptor CPU vs GPU ($Steps steps) ============"
    "{0,-18} {1,10} {2,10}" -f 'Version', 'Time (s)', 'FPS' | Write-Host
    "{0,-18} {1,10:N2} {2,10:N1}" -f $cpu.Label, $cpu.Seconds, $cpu.FPS | Write-Host
    "{0,-18} {1,10:N2} {2,10:N1}" -f $gpu.Label, $gpu.Seconds, $gpu.FPS | Write-Host
    Write-Host ("-" * 40)
    Write-Host ("Speedup (GPU / CPU): {0:N1}x" -f $speedup)
}
