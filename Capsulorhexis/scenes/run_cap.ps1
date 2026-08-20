<#
    Launch the cap-on-lens capsulorhexis demo in the runSofa GUI. Stock SOFA only
    (no Capsulorhexis.dll). Regenerates the meshes first.

    DEFAULT is cap_membrane.py -- the membrane simply SITS on the oblate lens, held down
    by a breakable adhesion. NOTHING is clamped (FIX_OUTER_RIM=False), so you can
    Shift+left-drag the RIM, lift it and FOLD IT OVER. Pull gently and the adhesion
    holds; pull harder and that spot peels off. It prints [Peel]/[ClothToPaper] lines.

    Usage:  ./scenes/run_cap.ps1                    # mass-spring (default, tuned)
            ./scenes/run_cap.ps1 -Fem              # co-rotational FEM
            ./scenes/run_cap.ps1 -Heatmap          # + live force-field UI in the browser
            ./scenes/run_cap.ps1 -SofaHeatmap -Gui qt   # SOFA's OWN heatmap (DataDisplay),
                                                        # in the Qt GUI (imgui crashes it)
            ./scenes/run_cap.ps1 -NoLog            # no stdout tee (max FPS, best for feel)
#>
[CmdletBinding()]
param(
    [string]$Scene = "cap_membrane.py",
    # -Fem runs the membrane with the co-rotational FEM instead of the default mass-spring.
    # Read by cap_membrane.py via CAP_MODE; everything else in the scene is identical.
    [switch]$Fem,
    # -Heatmap leaves the SOFA deformation view unchanged and additionally serves a live
    # sigma1 force-field map at http://127.0.0.1:8790/ (auto-opened in your browser): hover
    # a triangle for stress + crack direction; every frame is recorded, so drag freely and
    # scrub the timeline to review any past moment (Space = live/replay). The ACTUAL tear is
    # drawn on the disc as a magenta chain of mesh edges (a crack IS a chain of edges here),
    # with the live tip marked, and every frame carries it -- so the timeline replays the tear
    # edge by edge and the HUD shows +N/0 growth. The full field is also logged to
    # scenes/stress_log_<take>.jsonl for offline analysis. Via CAP_HEATMAP.
    [switch]$Heatmap,
    # -Tear enables real mesh tearing: a cystotome nick is seeded near the centre and the
    # crack advances from its tip along the INRIA argmax-c direction as you pull. The pull
    # mechanics are unchanged (still the tuned mass-spring, rim NOT anchored). -Thresh sets
    # sigma_bar_T. Via CAP_TEAR / CAP_TEAR_THRESH.
    [switch]$Tear,
    # sigma_bar_T, the capsule's toughness. Swept on an identical pull: 20 gives a long
    # smooth tear (563 vertices) with the mesh healthy, 220 a controlled one (179), 600
    # barely tears. Going far BELOW 20 makes it worse, not easier -- at 1 the mesh shreds
    # into 24.8% degenerate elements and the tear stalls SHORTER (204); CAP_TEAR_DEGEN_MAX
    # now brakes that. Raise for a tougher capsule, lower for a more fragile one.
    [double]$Thresh = 20.0,
    # -SofaHeatmap turns on SOFA's built-in DataDisplay + OglColorMap, colouring the
    # DEFORMING 3D mesh by sigma1 (CAP_STRESS_COLOR). It SIGABRTs the imgui GUI, so pair it
    # with -Gui qt (or glfw). This is the in-SOFA counterpart to the browser -Heatmap.
    [switch]$SofaHeatmap,
    # -Gui picks the GUI backend: imgui (default), qt, or glfw. imgui is the tuned one but
    # cannot render DataDisplay; qt/glfw can.
    [string]$Gui = "imgui",
    # -NoLog skips the Tee-Object mirror of stdout. PowerShell 5.1's Tee processes the stream
    # object-by-object, which costs real FPS on a chatty scene -- and FPS matters here beyond
    # smoothness: DISP_CLAMP limits per-STEP displacement while the mouse target moves in REAL
    # time, so a slower loop means the cursor travels further between steps, more nodes hit the
    # clamp, and you see the whole sheet snap inward. Use -NoLog when judging interactive feel.
    [switch]$NoLog
)
if ($Fem) { $env:CAP_MODE = "fem" } else { $env:CAP_MODE = "spring" }
if ($Heatmap) { $env:CAP_HEATMAP = "1" } else { $env:CAP_HEATMAP = "0" }
if ($Tear) { $env:CAP_TEAR = "1"; $env:CAP_TEAR_THRESH = "$Thresh" } else { $env:CAP_TEAR = "0" }
if ($SofaHeatmap) { $env:CAP_STRESS_COLOR = "1" } else { $env:CAP_STRESS_COLOR = "0" }
if ($SofaHeatmap -and $Gui -eq "imgui") {
    Write-Host "NOTE: SOFA's DataDisplay heatmap crashes the imgui GUI; switching -Gui glfw." -ForegroundColor Yellow
    $Gui = "glfw"
}
# Plugins to load. SofaPython3 is always needed to run the .py scene; the Qt GUI lives in a
# plugin that is NOT auto-registered, so load it when asked (glfw/imgui are built in).
$PluginArgs = @("-l", "SofaPython3")
if ($Gui -eq "qt") { $PluginArgs += @("-l", "Sofa.Qt") }

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
        & $runSofa @PluginArgs -g $Gui -a (Join-Path $ScenesDir $Scene)
    } else {
    # NOTE: do NOT add -Encoding here. Windows PowerShell 5.1's Tee-Object has no -Encoding
    # parameter (it only gained one in PowerShell 6), so passing it aborts the launch. The log
    # therefore lands as UTF-16; read it with a decoder rather than plain grep.
        & $runSofa @PluginArgs -g $Gui -a (Join-Path $ScenesDir $Scene) |
            Tee-Object -FilePath $LogPath
    }
} finally {
    $ErrorActionPreference = $prevEAP
}
