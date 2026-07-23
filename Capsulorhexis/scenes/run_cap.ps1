<#
    Launch the cap-on-lens capsulorhexis demo in the runSofa GUI. Stock SOFA only
    (no Capsulorhexis.dll). Regenerates the meshes first.

    DEFAULT is cap_membrane.py -- the membrane simply SITS on the oblate lens, held down
    by a breakable adhesion. NOTHING is clamped (FIX_OUTER_RIM=False), so you can
    Shift+left-drag the RIM, lift it and FOLD IT OVER. Pull gently and the adhesion
    holds; pull harder and that spot peels off. It prints [Peel]/[ClothToPaper] lines.

    Usage:  ./scenes/run_cap.ps1            # mass-spring (default, tuned)
            ./scenes/run_cap.ps1 -Fem       # co-rotational FEM
            ./scenes/run_cap.ps1 -NoLog     # no stdout tee (max FPS, best for judging feel)
#>
[CmdletBinding()]
param(
    [string]$Scene = "cap_membrane.py",
    # -Fem runs the membrane with the co-rotational FEM instead of the default mass-spring.
    # Read by cap_membrane.py via CAP_MODE; everything else in the scene is identical.
    [switch]$Fem,
    # -NoLog skips the Tee-Object mirror of stdout. PowerShell 5.1's Tee processes the stream
    # object-by-object, which costs real FPS on a chatty scene -- and FPS matters here beyond
    # smoothness: DISP_CLAMP limits per-STEP displacement while the mouse target moves in REAL
    # time, so a slower loop means the cursor travels further between steps, more nodes hit the
    # clamp, and you see the whole sheet snap inward. Use -NoLog when judging interactive feel.
    [switch]$NoLog
)
if ($Fem) { $env:CAP_MODE = "fem" } else { $env:CAP_MODE = "spring" }

$ErrorActionPreference = "Stop"
if (-not $env:SOFA_ROOT) { $env:SOFA_ROOT = "C:\SOFA\SOFA_v25.12.00_Win64" }
$ScenesDir = $PSScriptRoot

# ALWAYS regenerate. Only regenerating when cap.obj was missing meant that editing the
# geometry (C = flatness, CAP_ANGLE_DEG = coverage, A = size, TARGET_EDGE = resolution)
# silently did nothing, because the stale mesh was reused.
& py -3.12 (Join-Path $ScenesDir "generate_cap.py")

$runSofa = Join-Path $env:SOFA_ROOT "bin\runSofa.exe"
if (-not (Test-Path $runSofa)) { throw "runSofa not found at $runSofa" }

# Mirror everything runSofa prints to a FIXED log file as well as the console, so the last
# run can always be inspected afterwards without copy-pasting the terminal. Overwritten each
# launch; keep the previous one as .prev.log so a crash-then-relaunch does not lose evidence.
$LogPath = Join-Path $ScenesDir "last_run.log"
$PrevLog = Join-Path $ScenesDir "last_run.prev.log"
if (Test-Path $LogPath) { Move-Item -Force $LogPath $PrevLog }

Write-Host "Launching runSofa on $Scene ..." -ForegroundColor Green
Write-Host "Log -> $LogPath" -ForegroundColor DarkGray

# Keep Python's prints unbuffered: piping stdout into Tee-Object makes it a non-tty, and a
# block-buffered interpreter would leave the log empty until the process exits.
$env:PYTHONUNBUFFERED = "1"

# Do NOT use `2>&1` on a native exe here. Windows PowerShell 5.1 wraps every stderr line of a
# native command in a NativeCommandError; combined with the `$ErrorActionPreference = "Stop"`
# at the top of this script, one harmless line (e.g. "DeprecationWarning: scipy.misc is
# deprecated") becomes a TERMINATING error and the script dies before the GUI even opens.
# Tee stdout only -- that is where all the [sigma1]/[Peel]/[Runaway] diagnostics go -- and
# relax the preference for the duration of the call so a stray stderr line cannot kill it.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    if ($NoLog) {
        & $runSofa -l SofaPython3 -g imgui -a (Join-Path $ScenesDir $Scene)
    } else {
    # NOTE: do NOT add -Encoding here. Windows PowerShell 5.1's Tee-Object has no -Encoding
    # parameter (it only gained one in PowerShell 6), so passing it aborts the launch. The log
    # therefore lands as UTF-16; read it with a decoder rather than plain grep.
        & $runSofa -l SofaPython3 -g imgui -a (Join-Path $ScenesDir $Scene) |
            Tee-Object -FilePath $LogPath
    }
} finally {
    $ErrorActionPreference = $prevEAP
}
