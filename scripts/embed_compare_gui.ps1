<#
.SYNOPSIS
    Single host window with TWO live SOFA viewports side by side: raptor on CPU
    (left) and raptor on GPU (right), both animating. You watch the CPU one
    stutter next to the smooth GPU one — the FPS gap made visible.

.DESCRIPTION
    Launches two runSofa GUI processes (animation auto-started), finds each one's
    OpenGL window reliably (EnumWindows by PID, skipping the console window), then
    re-parents both into panels inside one host form via Win32 SetParent. Closing
    the host kills both simulations.

    By default it softens the raptor (low Young's modulus) so the motion is
    obvious — the stiff benchmark version barely moves. Use -Stiff for the
    original scenes. For hard FPS numbers use scripts/fps_compare_gui.ps1.

.PARAMETER SofaRoot
    SOFA install root. Auto-detected; override with -SofaRoot if needed.

.PARAMETER Stiff
    Use the original (stiff) raptor scenes instead of the softened, wobbly ones.

.EXAMPLE
    powershell -NoProfile -File scripts/embed_compare_gui.ps1
    powershell -NoProfile -File scripts/embed_compare_gui.ps1 -Stiff
#>
param(
    [string]$SofaRoot = 'C:\SOFA\SOFA_v25.12.00_Win64',
    [switch]$Stiff
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- Win32 interop -------------------------------------------------------
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Win32 {
    [DllImport("user32.dll")] public static extern IntPtr SetParent(IntPtr c, IntPtr p);
    [DllImport("user32.dll")] public static extern int  GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern int  SetWindowLong(IntPtr h, int i, int v);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool r);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);

    const int GWL_STYLE = -16;
    const int WS_CHILD       = 0x40000000;
    const int WS_POPUP       = unchecked((int)0x80000000);
    const int WS_CAPTION     = 0x00C00000;
    const int WS_THICKFRAME  = 0x00040000;
    const int WS_MINIMIZEBOX = 0x00020000;
    const int WS_MAXIMIZEBOX = 0x00010000;
    const int WS_SYSMENU     = 0x00080000;
    const int SW_SHOW = 5;

    static readonly EnumProc _cb = _Cb;
    static uint _pid; static IntPtr _found;
    static bool _Cb(IntPtr h, IntPtr l){
        uint pid; GetWindowThreadProcessId(h, out pid);
        if(pid==_pid && IsWindowVisible(h) && GetParent(h)==IntPtr.Zero){
            var sb = new StringBuilder(64); GetClassName(h, sb, 64);
            string cn = sb.ToString();
            if(cn != "ConsoleWindowClass" && cn != "IME" && cn != "MSCTFIME UI"){ _found = h; return false; }
        }
        return true;
    }
    public static IntPtr FindGlWindow(uint pid){
        _pid = pid; _found = IntPtr.Zero;
        EnumWindows(_cb, IntPtr.Zero);
        return _found;
    }
    public static void Embed(IntPtr child, IntPtr parent, int w, int h){
        int s = GetWindowLong(child, GWL_STYLE);
        s &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU);
        s |= WS_CHILD;
        SetWindowLong(child, GWL_STYLE, s);
        SetParent(child, parent);
        MoveWindow(child, 0, 0, w, h, true);
        ShowWindow(child, SW_SHOW);
    }
    public static void Fill(IntPtr child, int w, int h){ MoveWindow(child, 0, 0, w, h, true); }
}
'@

# --- resolve paths -------------------------------------------------------
$runSofa = Join-Path $SofaRoot 'bin\runSofa.exe'
if (-not (Test-Path $runSofa)) {
    $c = Get-Command runSofa -ErrorAction SilentlyContinue
    if ($c) { $runSofa = $c.Source }
    else { [System.Windows.Forms.MessageBox]::Show("runSofa.exe not found. Pass -SofaRoot."); return }
}
$dir = Join-Path $SofaRoot 'plugins\SofaCUDA\share\sofa\examples\SofaCUDA'
$cpuScene = Join-Path $dir 'raptor-cpu.scn'
$gpuScene = Join-Path $dir 'raptor-cuda.scn'

# Soften the raptor so the motion is obvious (stiff benchmark scenes barely move).
# Mesh paths are relative and resolve through SOFA's data repository regardless of
# where the .scn lives, so a temp copy works fine.
function New-SoftScene($src){
    $t = Get-Content -Raw $src
    $t = $t -replace 'value="100000"',  'value="600"'
    $t = $t -replace 'value="1000000"', 'value="3000"'
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("raptor_soft_" + [System.IO.Path]::GetFileNameWithoutExtension($src) + ".scn")
    [System.IO.File]::WriteAllText($tmp, $t)
    return $tmp
}
if (-not $Stiff) {
    $cpuScene = New-SoftScene $cpuScene
    $gpuScene = New-SoftScene $gpuScene
}

# --- palette -------------------------------------------------------------
$bg    = [System.Drawing.Color]::FromArgb(13,17,23)
$fg    = [System.Drawing.Color]::FromArgb(230,237,243)
$dim   = [System.Drawing.Color]::FromArgb(139,148,158)
$green = [System.Drawing.Color]::FromArgb(63,185,80)
$grey  = [System.Drawing.Color]::FromArgb(150,157,165)

# --- host form -----------------------------------------------------------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'raptor  CPU vs GPU  —  並排即時模擬'
$form.ClientSize = New-Object System.Drawing.Size(1320,720)
$form.BackColor = $bg
$form.Font = New-Object System.Drawing.Font('Segoe UI',10)
$form.StartPosition = 'CenterScreen'

$hCpu = New-Object System.Windows.Forms.Label
$hCpu.Text = 'CPU  (Vec3d)  —  會卡頓'
$hCpu.ForeColor = $grey; $hCpu.Font = New-Object System.Drawing.Font('Segoe UI',12,[System.Drawing.FontStyle]::Bold)
$hCpu.Location = New-Object System.Drawing.Point(12,8); $hCpu.AutoSize = $true
$form.Controls.Add($hCpu)

$hGpu = New-Object System.Windows.Forms.Label
$hGpu.Text = 'GPU  (CudaVec3f)  —  流暢'
$hGpu.ForeColor = $green; $hGpu.Font = New-Object System.Drawing.Font('Segoe UI',12,[System.Drawing.FontStyle]::Bold)
$hGpu.Location = New-Object System.Drawing.Point(676,8); $hGpu.AutoSize = $true
$form.Controls.Add($hGpu)

$panL = New-Object System.Windows.Forms.Panel
$panL.Location = New-Object System.Drawing.Point(8,38)
$panL.Size = New-Object System.Drawing.Size(648,640)
$panL.BackColor = [System.Drawing.Color]::Black
$form.Controls.Add($panL)

$panR = New-Object System.Windows.Forms.Panel
$panR.Location = New-Object System.Drawing.Point(664,38)
$panR.Size = New-Object System.Drawing.Size(648,640)
$panR.BackColor = [System.Drawing.Color]::Black
$form.Controls.Add($panR)

$foot = New-Object System.Windows.Forms.Label
$foot.Text = '正在啟動兩個模擬…（軟化版,會明顯晃動）拖曳旋轉視角;Shift+左鍵抓住 raptor 拉扯。硬 FPS 數字用 fps_compare_gui.ps1。'
$foot.ForeColor = $dim; $foot.Location = New-Object System.Drawing.Point(12,686); $foot.AutoSize = $true
$form.Controls.Add($foot)

# --- launch both SOFA processes (animation auto-started) ----------------
# Stagger the two launches: two runSofa GUIs initializing their OpenGL contexts
# at the exact same instant can race, and one loses its context and exits.
# A few seconds between them lets each finish GL init cleanly.
$pCpu = Start-Process -FilePath $runSofa -ArgumentList @('-a', "`"$cpuScene`"") -PassThru
Start-Sleep -Seconds 4
$pGpu = Start-Process -FilePath $runSofa -ArgumentList @('-a', "`"$gpuScene`"") -PassThru

$script:E = @{ cpuH=[IntPtr]::Zero; gpuH=[IntPtr]::Zero }

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({
    if($script:E.cpuH -eq [IntPtr]::Zero -and -not $pCpu.HasExited){
        $h = [Win32]::FindGlWindow([uint32]$pCpu.Id)
        if($h -ne [IntPtr]::Zero){ [Win32]::Embed($h, $panL.Handle, $panL.Width, $panL.Height); $script:E.cpuH = $h }
    }
    if($script:E.gpuH -eq [IntPtr]::Zero -and -not $pGpu.HasExited){
        $h = [Win32]::FindGlWindow([uint32]$pGpu.Id)
        if($h -ne [IntPtr]::Zero){ [Win32]::Embed($h, $panR.Handle, $panR.Width, $panR.Height); $script:E.gpuH = $h }
    }
    if($script:E.cpuH -ne [IntPtr]::Zero -and $script:E.gpuH -ne [IntPtr]::Zero){
        $timer.Stop()
        $foot.Text = '兩個模擬已嵌入。左邊 CPU 明顯卡、右邊 GPU 流暢 = 那 ~28× 的直觀版。硬 FPS 數字用 fps_compare_gui.ps1。'
    }
})
$timer.Start()

# --- resize: keep children filling their panels --------------------------
$form.Add_Resize({
    $w = [int](($form.ClientSize.Width - 24) / 2)
    $h = $form.ClientSize.Height - 82
    if($w -lt 50 -or $h -lt 50){ return }
    $panL.Size = New-Object System.Drawing.Size($w,$h)
    $panR.Location = New-Object System.Drawing.Point(($w+16),38)
    $panR.Size = New-Object System.Drawing.Size($w,$h)
    $hGpu.Location = New-Object System.Drawing.Point(($w+20),8)
    $foot.Location = New-Object System.Drawing.Point(12,($h+46))
    if($script:E.cpuH -ne [IntPtr]::Zero){ [Win32]::Fill($script:E.cpuH,$panL.Width,$panL.Height) }
    if($script:E.gpuH -ne [IntPtr]::Zero){ [Win32]::Fill($script:E.gpuH,$panR.Width,$panR.Height) }
})

# --- cleanup: kill both simulations when host closes --------------------
$form.Add_FormClosing({
    foreach($p in @($pCpu,$pGpu)){
        try { if($p -and -not $p.HasExited){ $p.Kill() } } catch {}
    }
})

[void]$form.ShowDialog()
