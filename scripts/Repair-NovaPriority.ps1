#Requires -Version 5.1
<#
.SYNOPSIS
  Show, and with -Apply raise, the priority of Nova's running trading path.

.DESCRIPTION
  Lists the API (:8000), the IB Gateway (:4001 / :4002) with the IBC loop that
  relaunches it, Vite (:5173), the localhost watchdog and the installed desk's
  main process, each with its CPU class, I/O priority and memory priority, and
  the Nova scheduled tasks with their Priority setting.

  -Apply raises every one under Normal to Normal in place: nothing restarts,
  and the Gateway keeps its login. It never lowers anything.

  Why it exists: a running process keeps the priority it started with, and its
  children inherit it. Re-registering the tasks at priority 4 reaches only
  processes they start next. The IBC loop that NovaDailyStart started at logon
  on 2026-09-28 relaunches every Gateway, IBC's nightly restart included, at
  its own BelowNormal CPU, Low I/O and memory priority 2, until IBC itself
  restarts, which costs a phone login.

.PARAMETER Apply
  Raise what reads below Normal. Without it the script only reads.

.PARAMETER ProcessId
  Act on these processes instead of finding Nova's: pids separated by commas
  (a string, because powershell.exe -File cannot pass an array).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Repair-NovaPriority.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Repair-NovaPriority.ps1 -Apply
#>
param(
  [switch]$Apply,
  [string]$ProcessId = ''
)
$ErrorActionPreference = 'Continue'
$chosen = @($ProcessId -split '[,\s]+' | Where-Object { $_ } | ForEach-Object { [int]$_ })
. (Join-Path $PSScriptRoot 'NovaProcessPriority.ps1')
if (-not (Initialize-NovaPriorityNative)) {
  Write-Host "Cannot read process priority: $($script:NovaPriorityNativeError)" -ForegroundColor Red
  exit 2
}

# Task -> the Priority it should have (4 Normal; 7 BelowNormal, on purpose for maintenance).
$expectedTasks = [ordered]@{
  NovaLocalhostWatchdog = 4
  NovaDailyStart = 4
  NovaMorningCheck = 4
  NovaRepoHygiene = 7
}
$apiPort = 8000
$vitePort = 5173
$gatewayPorts = @(4001, 4002)
# Command lines of the IBC launch chain above the Gateway's java.exe.
$ibcPattern = '(?i)\\IBC\\|StartGateway|start_gateway|DisplayBannerAndLaunch|ibcstart'

function Get-NovaListeners {
  # Port -> owning pids, from netstat (Get-NetTCPConnection fails in some contexts).
  $map = @{}
  foreach ($line in (netstat -ano 2>$null)) {
    if ($line -match '^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$') {
      $port = [int]$Matches[2]
      if (-not $map.ContainsKey($port)) { $map[$port] = @() }
      if ($map[$port] -notcontains [int]$Matches[3]) { $map[$port] += [int]$Matches[3] }
    }
  }
  return $map
}

$all = @{}
Get-CimInstance Win32_Process | ForEach-Object { $all[[int]$_.ProcessId] = $_ }

function Get-NovaPortPids([hashtable]$Listeners, [int]$Port) {
  if ($Listeners.ContainsKey($Port)) { return @($Listeners[$Port]) }
  return @()
}

function Get-NovaChildren([int]$Id) {
  # Started after their parent, so a reused pid is never taken for a child.
  if ($Id -le 0) { return @() }
  $parent = $all[$Id]
  if (-not $parent) { return @() }
  $kids = @($all.Values | Where-Object {
      [int]$_.ParentProcessId -eq $Id -and $_.CreationDate -ge $parent.CreationDate
    })
  $out = @()
  foreach ($kid in $kids) { $out += [int]$kid.ProcessId; $out += Get-NovaChildren ([int]$kid.ProcessId) }
  return $out
}

function Get-NovaIbcLoop([int]$Id) {
  # The IBC launch chain above the Gateway: it relaunches java.exe at IBC's restarts.
  $out = @()
  $child = $all[$Id]
  while ($child) {
    $parent = $all[[int]$child.ParentProcessId]
    if (-not $parent -or $parent.CreationDate -gt $child.CreationDate) { break }
    if ([string]$parent.CommandLine -notmatch $ibcPattern) { break }
    $out += [int]$parent.ProcessId
    $child = $parent
  }
  return $out
}

$targets = New-Object System.Collections.Generic.List[object]
function Add-NovaTarget([string]$Role, [int]$Id) {
  if ($Id -le 0 -or -not $all.ContainsKey($Id)) { return }
  if ($targets | Where-Object { $_.ProcessId -eq $Id }) { return }
  $targets.Add([pscustomobject]@{ Role = $Role; ProcessId = $Id; Name = $all[$Id].Name })
}

if ($chosen.Count) {
  foreach ($id in $chosen) { Add-NovaTarget 'chosen' $id }
} else {
  $listeners = Get-NovaListeners
  foreach ($id in (Get-NovaPortPids $listeners $apiPort)) {
    Add-NovaTarget 'API' $id
    foreach ($kid in (Get-NovaChildren $id)) { Add-NovaTarget 'API child' $kid }
  }
  foreach ($port in $gatewayPorts) {
    foreach ($id in (Get-NovaPortPids $listeners $port)) {
      Add-NovaTarget "Gateway :$port" $id
      foreach ($loop in (Get-NovaIbcLoop $id)) { Add-NovaTarget 'IBC loop' $loop }
    }
  }
  foreach ($id in (Get-NovaPortPids $listeners $vitePort)) {
    Add-NovaTarget 'Vite' $id
    foreach ($kid in (Get-NovaChildren $id)) { Add-NovaTarget 'Vite child' $kid }
  }
  $all.Values | Where-Object { $_.Name -eq 'powershell.exe' -and [string]$_.CommandLine -match 'Watch-NovaLocalhost\.ps1' } |
    ForEach-Object { Add-NovaTarget 'watchdog' ([int]$_.ProcessId) }
  # The desk's main process; Chromium sets its helper processes' priority itself.
  $all.Values | Where-Object { $_.Name -eq 'Nova.exe' -and [string]$_.CommandLine -notmatch '--type=' } |
    ForEach-Object { Add-NovaTarget 'desk' ([int]$_.ProcessId) }
}

$below = 0
$failed = 0
Write-Host ''
Write-Host 'Processes:' -ForegroundColor Cyan
if (-not $targets.Count) { Write-Host '  none found' }
foreach ($t in $targets) {
  $values = [NovaProcessPriorityNative]::Read($t.ProcessId)
  $low = Test-NovaPriorityLow $values
  if ($low) { $below++ }
  $line = '  {0,-14} {1,6} {2,-16} {3}' -f $t.Role, $t.ProcessId, $t.Name, (Format-NovaPriority $values)
  if ($Apply -and $low) {
    $result = Set-NovaNormalPriority -ProcessId $t.ProcessId
    if (-not $result.Ok) { $failed++ }
    $line = '  {0,-14} {1}' -f $t.Role, ($result.Text -replace '^pid ', '')
    Write-Host $line -ForegroundColor $(if ($result.Ok) { 'Green' } else { 'Red' })
  } else {
    Write-Host $line -ForegroundColor $(if ($low) { 'Yellow' } else { 'Gray' })
  }
}

$tasksWrong = 0
if (-not $chosen.Count) {
  Write-Host ''
  Write-Host 'Scheduled tasks:' -ForegroundColor Cyan
  foreach ($name in $expectedTasks.Keys) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { Write-Host ('  {0,-22} not registered' -f $name); continue }
    $want = $expectedTasks[$name]
    $have = $task.Settings.Priority
    if ($have -ne $want) { $tasksWrong++ }
    $note = if ($have -eq $want) { 'ok' } else { "should be $want" }
    Write-Host ('  {0,-22} priority {1}  {2}' -f $name, $have, $note) -ForegroundColor $(if ($have -eq $want) { 'Gray' } else { 'Yellow' })
  }
}

Write-Host ''
if ($Apply) {
  if ($failed) {
    Write-Host "$failed process(es) still read below Normal." -ForegroundColor Red
  } else {
    Write-Host 'Done. Nothing was restarted.' -ForegroundColor Green
  }
} elseif ($below) {
  $again = if ($chosen.Count) { " -ProcessId $ProcessId" } else { '' }
  Write-Host "$below process(es) read below Normal. Raise them in place (nothing restarts, the Gateway keeps its login):" -ForegroundColor Yellow
  Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\Repair-NovaPriority.ps1 -Apply$again"
}
if ($tasksWrong) {
  Write-Host 'A task starts its processes at its Priority setting. Re-register (nothing stops or restarts):' -ForegroundColor Yellow
  Write-Host '  powershell -ExecutionPolicy Bypass -File scripts\Register-NovaLocalhostWatchdog.ps1'
  Write-Host '  powershell -ExecutionPolicy Bypass -File scripts\Install-NovaDailyTask.ps1'
}
if ($failed) { exit 1 }
exit 0
