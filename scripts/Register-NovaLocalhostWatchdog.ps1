#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$repo = if ($env:NOVA_REPO) { $env:NOVA_REPO } else { 'C:\Users\aalta\github\Nova' }
$watch = Join-Path $repo 'scripts\Watch-NovaLocalhost.ps1'
$taskName = 'NovaLocalhostWatchdog'
$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watch`" -IntervalSec 20"
# -WindowStyle Hidden hides the console only after it has drawn: a black window flashed on
# every 5-minute kick (2026-10-01: 103 that day, each a duplicate that exits at once). A
# headless conhost gives PowerShell a console with no window at all.
$conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'

# Unregistering leaves a running watchdog, and the API and Vite it started, running.
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $conhost -Argument "--headless `"$ps`" $arg"
$tLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# Kick every 5 minutes for a year - mutex makes extras no-ops if watch already looping
# (a watchdog Task Scheduler did not start -- this script's, or one that restarted itself on
# new code -- is not the task's, so IgnoreNew does not hold the kicks back)
$tRepeat = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Days 365)
# Priority 4 is Normal CPU, I/O and memory priority. Without it Task Scheduler uses 7:
# BelowNormal CPU, Low I/O and memory priority 2, which the API and Vite inherit
# (2026-10-01: the live API ran that way).
$settings = New-ScheduledTaskSettingsSet `
  -Priority 4 `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action `
  -Trigger @($tLogon, $tRepeat) -Settings $settings -Principal $principal -Force | Out-Null

# Detached long-running watch now (it exits at once while one is already running)
Start-Process -FilePath $ps -ArgumentList $arg -WindowStyle Hidden
Start-Sleep 4
Write-Host 'Task:'
Get-ScheduledTask -TaskName $taskName |
  Select-Object TaskName, State, @{ Name = 'Priority'; Expression = { $_.Settings.Priority } } |
  Format-Table -AutoSize
Write-Host 'Watch processes:'
. (Join-Path $PSScriptRoot 'NovaProcessPriority.ps1')
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -match 'Watch-NovaLocalhost' } |
  ForEach-Object {
    $values = Get-NovaProcessPriority -ProcessId $_.ProcessId
    [pscustomobject]@{
      ProcessId = $_.ProcessId
      Priority = if ($values) { Format-NovaPriority $values } else { 'unknown' }
    }
  } | Format-Table -AutoSize
