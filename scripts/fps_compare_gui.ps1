<#
.SYNOPSIS
    Single-window FPS dashboard: run the raptor scene on CPU and GPU and compare
    them side-by-side inside ONE window (no need to read SOFA's own UI).

.DESCRIPTION
    Press "跑 Benchmark". The tool runs raptor-cpu.scn then raptor-cuda.scn
    headless (batch) for the chosen number of steps, parses each run's FPS, and
    draws two bars + the speedup factor. The window stays responsive while the
    runs happen in the background (polled by a timer).

.PARAMETER SofaRoot
    SOFA install root. Auto-detected; override if yours lives elsewhere.

.PARAMETER Steps
    Default step count shown in the spinner. 300 gives a stable steady-state FPS.

.EXAMPLE
    powershell -NoProfile -File scripts/fps_compare_gui.ps1
#>
param(
    [string]$SofaRoot = 'C:\SOFA\SOFA_v25.12.00_Win64',
    [int]$Steps = 300
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

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

# --- palette (GitHub dark) ----------------------------------------------
$bg     = [System.Drawing.Color]::FromArgb(13,17,23)
$panel  = [System.Drawing.Color]::FromArgb(22,27,34)
$fg     = [System.Drawing.Color]::FromArgb(230,237,243)
$dim    = [System.Drawing.Color]::FromArgb(139,148,158)
$grey   = [System.Drawing.Color]::FromArgb(110,118,129)
$green  = [System.Drawing.Color]::FromArgb(63,185,80)
$accent = [System.Drawing.Color]::FromArgb(88,166,255)
$track  = [System.Drawing.Color]::FromArgb(48,54,61)

# --- form ----------------------------------------------------------------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'raptor  CPU vs GPU  —  FPS 對比'
$form.ClientSize = New-Object System.Drawing.Size(640,420)
$form.BackColor = $bg
$form.Font = New-Object System.Drawing.Font('Segoe UI',10)
$form.StartPosition = 'CenterScreen'

function New-Label($text,$x,$y,$w,$h,$color,$size,$bold){
    $l = New-Object System.Windows.Forms.Label
    $l.Text=$text; $l.Location=New-Object System.Drawing.Point($x,$y)
    $l.Size=New-Object System.Drawing.Size($w,$h); $l.ForeColor=$color
    $style = if($bold){[System.Drawing.FontStyle]::Bold}else{[System.Drawing.FontStyle]::Regular}
    $l.Font=New-Object System.Drawing.Font('Segoe UI',$size,$style)
    $form.Controls.Add($l); return $l
}

New-Label 'raptor  ·  19,409 四面體  ·  co-rotational FEM  ·  隱式 Euler + CG' 20 14 600 20 $dim 9.5 $false | Out-Null
New-Label '唯一差別:template  Vec3d(CPU)  ↔  CudaVec3f(GPU)。物理/求解器全相同。' 20 34 600 20 $dim 9.5 $false | Out-Null

# steps spinner + run button
New-Label '步數' 20 70 40 24 $fg 10 $false | Out-Null
$spin = New-Object System.Windows.Forms.NumericUpDown
$spin.Location = New-Object System.Drawing.Point(64,68)
$spin.Size = New-Object System.Drawing.Size(80,26)
$spin.Minimum = 50; $spin.Maximum = 2000; $spin.Increment = 50; $spin.Value = $Steps
$spin.BackColor = $panel; $spin.ForeColor = $fg
$form.Controls.Add($spin)

$btn = New-Object System.Windows.Forms.Button
$btn.Text = '▶  跑 Benchmark'
$btn.Location = New-Object System.Drawing.Point(160,66)
$btn.Size = New-Object System.Drawing.Size(150,30)
$btn.FlatStyle = 'Flat'; $btn.BackColor = $accent; $btn.ForeColor = [System.Drawing.Color]::Black
$btn.FlatAppearance.BorderSize = 0
$form.Controls.Add($btn)

New-Label 'CPU 那次要跑一會兒(3070 上 300 步約 60 秒)' 320 74 300 20 $dim 9 $false | Out-Null

# --- bars ----------------------------------------------------------------
$barX = 130; $barW = 380; $barH = 34
function New-BarRow($name,$y,$barColor){
    New-Label $name 20 ($y+6) 105 24 $fg 10 $true | Out-Null
    $bgp = New-Object System.Windows.Forms.Panel
    $bgp.Location = New-Object System.Drawing.Point($barX,$y)
    $bgp.Size = New-Object System.Drawing.Size($barW,$barH)
    $bgp.BackColor = $track
    $form.Controls.Add($bgp)
    $bar = New-Object System.Windows.Forms.Panel
    $bar.Location = New-Object System.Drawing.Point($barX,$y)
    $bar.Size = New-Object System.Drawing.Size(0,$barH)
    $bar.BackColor = $barColor
    $form.Controls.Add($bar); $bar.BringToFront()
    $lbl = New-Label '—' ($barX+$barW+12) ($y+6) 100 24 $fg 12 $true
    return @{ Bar=$bar; Lbl=$lbl }
}
$cpuRow = New-BarRow 'CPU  (Vec3d)'      130 $grey
$gpuRow = New-BarRow 'GPU  (CudaVec3f)'  178 $green

# speedup
$lblSpeed = New-Label '' 20 232 600 46 $accent 26 $true

# status + progress
$prog = New-Object System.Windows.Forms.ProgressBar
$prog.Location = New-Object System.Drawing.Point(20,300)
$prog.Size = New-Object System.Drawing.Size(600,16)
$prog.Style = 'Blocks'
$form.Controls.Add($prog)
$lblStatus = New-Label '按「跑 Benchmark」開始。' 20 322 600 22 $dim 9.5 $false

New-Label 'FPS 越高越好。長條以兩者中較大者為滿格。' 20 360 600 20 $dim 9 $false | Out-Null

# --- benchmark state / timer --------------------------------------------
$script:S = @{
    phase='idle'; proc=$null; cpuFps=$null; gpuFps=$null
    cpuOut=$null; cpuErr=$null; gpuOut=$null; gpuErr=$null
}

function Start-Scene($scene){
    $out = [System.IO.Path]::GetTempFileName()
    $err = [System.IO.Path]::GetTempFileName()
    $steps = [int]$spin.Value
    $p = Start-Process -FilePath $runSofa `
        -ArgumentList @('-g','batch','-n',"$steps","`"$scene`"") `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    return @{ Proc=$p; Out=$out; Err=$err }
}

function Read-Fps($out,$err){
    $raw = (Get-Content $out -Raw -ErrorAction SilentlyContinue) + "`n" +
           (Get-Content $err -Raw -ErrorAction SilentlyContinue)
    Remove-Item $out,$err -ErrorAction SilentlyContinue
    $m = [regex]::Match($raw,'iterations done in\s+([\d.]+)\s+s\s+\(\s+([\d.]+)\s+FPS')
    if($m.Success){ return [double]$m.Groups[2].Value } else { return $null }
}

function Update-Bars {
    $c = $script:S.cpuFps; $g = $script:S.gpuFps
    $vals = @(); if($c){$vals+=$c}; if($g){$vals+=$g}
    if($vals.Count -eq 0){ return }
    $max = ($vals | Measure-Object -Maximum).Maximum
    if($c){ $cpuRow.Bar.Width = [int]($barW * $c / $max); $cpuRow.Lbl.Text = ('{0:N1} FPS' -f $c) }
    if($g){ $gpuRow.Bar.Width = [int]($barW * $g / $max); $gpuRow.Lbl.Text = ('{0:N1} FPS' -f $g) }
    if($c -and $g){ $lblSpeed.Text = ('GPU 快 {0:N1}×' -f ($g/$c)) }
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 300
$timer.Add_Tick({
    if($script:S.proc -and -not $script:S.proc.HasExited){ return }

    if($script:S.phase -eq 'cpu'){
        $script:S.cpuFps = Read-Fps $script:S.cpuOut $script:S.cpuErr
        Update-Bars
        $r = Start-Scene $gpuScene
        $script:S.proc=$r.Proc; $script:S.gpuOut=$r.Out; $script:S.gpuErr=$r.Err
        $script:S.phase='gpu'
        $lblStatus.Text = 'Running GPU (CudaVec3f)… 很快'
    }
    elseif($script:S.phase -eq 'gpu'){
        $script:S.gpuFps = Read-Fps $script:S.gpuOut $script:S.gpuErr
        Update-Bars
        $script:S.phase='done'
        $timer.Stop()
        $prog.Style='Blocks'; $prog.Value=0
        $btn.Enabled=$true; $spin.Enabled=$true
        $lblStatus.Text = '完成。改步數再按一次可重跑。'
    }
})

$btn.Add_Click({
    $btn.Enabled=$false; $spin.Enabled=$false
    $lblSpeed.Text=''; $cpuRow.Bar.Width=0; $gpuRow.Bar.Width=0
    $cpuRow.Lbl.Text='…'; $gpuRow.Lbl.Text='…'
    $script:S.cpuFps=$null; $script:S.gpuFps=$null
    $prog.Style='Marquee'; $prog.MarqueeAnimationSpeed=30
    $lblStatus.Text = 'Running CPU (Vec3d)… 請稍候(這次最慢)'
    $r = Start-Scene $cpuScene
    $script:S.proc=$r.Proc; $script:S.cpuOut=$r.Out; $script:S.cpuErr=$r.Err
    $script:S.phase='cpu'
    $timer.Start()
})

[void]$form.ShowDialog()
