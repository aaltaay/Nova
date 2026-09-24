# Nova's "Updating" window.
#
# Shown by the desk (electron/updateSplash.mjs) the moment the operator picks
# "Restart to update". The installer runs silently and Nova is closed while it
# does, so without this window nothing of Nova is on screen for most of a
# minute (2026-09-23: 46 s on the desk PC, read as "nothing happened").
#
# It runs in its own PowerShell process so it outlives Nova, names the step it
# can see (Nova closing, the installer running, the new Nova starting), closes
# itself once the new version's window is up, and says what to do when that
# window does not come. It only reads process names and start times: it never
# touches the install folder, the installer or Nova. Nova closes it early (an
# install called off) by writing "<this script's path>.cancel".
#
# Keep this file ASCII: Windows PowerShell 5.1 reads a file without a BOM as ANSI.

param(
  [string]$Version = '',
  [string]$ProcessName = 'Nova',
  [string]$InstallerPattern = 'Nova-Setup*',
  [string]$LogPath = '',
  # No new Nova window by then: say so and offer Close (keeps watching).
  [int]$SlowAfterSec = 120,
  # The installer came and went and no Nova at all is running for this long.
  [int]$GoneAfterSec = 20,
  # Never linger longer than this.
  [int]$QuitAfterSec = 1800
)

$ErrorActionPreference = 'Stop'
$started = Get-Date
$cancelPath = "$PSCommandPath.cancel"

try {
  # Crisp text on a scaled monitor. Unaware still works; Windows stretches it.
  Add-Type -Namespace NovaUpdate -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
  [void][NovaUpdate.Dpi]::SetProcessDPIAware()
} catch {
  $null = $_
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$target = 'the update'
if ($Version) { $target = $Version }

# The desk's own colours (main.mjs backgroundColor #0b0f14).
$bg = [System.Drawing.Color]::FromArgb(11, 15, 20)
$edge = [System.Drawing.Color]::FromArgb(48, 56, 66)
$fg = [System.Drawing.Color]::FromArgb(230, 237, 243)
$dim = [System.Drawing.Color]::FromArgb(139, 148, 158)
$warn = [System.Drawing.Color]::FromArgb(240, 180, 80)

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Updating Nova'
$form.FormBorderStyle = 'None'
$form.ShowInTaskbar = $true
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.BackColor = $edge
$form.AutoSize = $true
$form.AutoSizeMode = 'GrowAndShrink'
$form.KeyPreview = $true

$graphics = $form.CreateGraphics()
$scale = $graphics.DpiX / 96.0
$graphics.Dispose()
function Px([int]$n) { [int][Math]::Round($n * $scale) }

$width = Px 380

$panel = New-Object System.Windows.Forms.FlowLayoutPanel
$panel.FlowDirection = 'TopDown'
$panel.WrapContents = $false
$panel.AutoSize = $true
$panel.AutoSizeMode = 'GrowAndShrink'
$panel.BackColor = $bg
$panel.Padding = New-Object System.Windows.Forms.Padding((Px 22), (Px 18), (Px 22), (Px 18))
$panel.Margin = New-Object System.Windows.Forms.Padding(1)
$form.Padding = New-Object System.Windows.Forms.Padding(0)
$form.Controls.Add($panel)

function New-Line([float]$points, [System.Drawing.FontStyle]$style, [System.Drawing.Color]$color, [int]$gapBelow) {
  $label = New-Object System.Windows.Forms.Label
  $label.AutoSize = $true
  $label.MaximumSize = New-Object System.Drawing.Size($width, 0)
  $label.Font = New-Object System.Drawing.Font('Segoe UI', $points, $style)
  $label.ForeColor = $color
  $label.BackColor = $bg
  $label.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, (Px $gapBelow))
  $panel.Controls.Add($label)
  return $label
}

$title = New-Line 12 ([System.Drawing.FontStyle]::Bold) $fg 10
$title.Text = "Updating Nova to $target"

$step = New-Line 10 ([System.Drawing.FontStyle]::Regular) $fg 8
$step.Text = 'Closing Nova...'

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Style = 'Marquee'
$bar.MarqueeAnimationSpeed = 30
$bar.Width = $width
$bar.Height = Px 6
$bar.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, (Px 12))
$panel.Controls.Add($bar)

$note = New-Line 9 ([System.Drawing.FontStyle]::Regular) $dim 0
$note.Text = 'Nova reopens by itself once the update is in, usually within a minute. Nothing to do.'

$close = New-Object System.Windows.Forms.Button
$close.Text = 'Close'
$close.AutoSize = $true
$close.FlatStyle = 'Flat'
$close.ForeColor = $fg
$close.BackColor = $bg
$close.Margin = New-Object System.Windows.Forms.Padding(0, (Px 14), 0, 0)
$close.Visible = $false
$close.Add_Click({ $form.Close() })
$panel.Controls.Add($close)

$form.Add_KeyDown({ if ($_.KeyCode -eq 'Escape' -and $close.Visible) { $form.Close() } })

function Get-Running([string]$name) {
  return @(Get-Process -Name $name -ErrorAction SilentlyContinue)
}

function Test-StartedSince($process) {
  try { return $process.StartTime -gt $started } catch { return $false }
}

$script:installerSeen = $false
$script:emptySince = $null
$script:stuck = $false

function Show-Stuck([string]$headline) {
  if ($script:stuck) { return }
  $script:stuck = $true
  $title.Text = $headline
  $title.ForeColor = $warn
  $step.Text = 'Open Nova from the Start menu.'
  $bar.Visible = $false
  $detail = 'This window closes by itself if Nova appears.'
  if ($LogPath) { $detail = "What happened is in $LogPath. $detail" }
  $note.Text = $detail
  $close.Visible = $true
  $form.TopMost = $false
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 500
$timer.Add_Tick({
  $elapsed = ((Get-Date) - $started).TotalSeconds
  $nova = Get-Running $ProcessName
  $fresh = @($nova | Where-Object { Test-StartedSince $_ })
  $old = @($nova | Where-Object { -not (Test-StartedSince $_) })

  if (@($fresh | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }).Count -gt 0) {
    $timer.Stop()
    $form.Close()
    return
  }
  if ($elapsed -ge $QuitAfterSec -or (Test-Path -LiteralPath $cancelPath)) {
    $timer.Stop()
    $form.Close()
    return
  }

  $installing = (Get-Running $InstallerPattern).Count -gt 0
  if ($installing) { $script:installerSeen = $true }

  if ($fresh.Count -gt 0) {
    $script:emptySince = $null
    if (-not $script:stuck) { $step.Text = "Starting Nova $Version..." }
  } elseif ($installing) {
    $script:emptySince = $null
    if (-not $script:stuck) { $step.Text = "Installing $target..." }
  } elseif ($old.Count -gt 0) {
    $script:emptySince = $null
    if (-not $script:stuck) { $step.Text = 'Closing Nova...' }
  } elseif ($script:installerSeen) {
    if ($null -eq $script:emptySince) { $script:emptySince = Get-Date }
    if (((Get-Date) - $script:emptySince).TotalSeconds -ge $GoneAfterSec) {
      Show-Stuck 'Nova did not reopen'
    }
  }

  if ($elapsed -ge $SlowAfterSec) { Show-Stuck 'Nova is taking longer than usual' }
})

$form.Add_Shown({ $form.Activate(); $timer.Start() })
[void]$form.ShowDialog()
$timer.Dispose()
$form.Dispose()
