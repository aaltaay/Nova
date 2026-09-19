#Requires -Version 5.1
<#
.SYNOPSIS
  Register (or update) a current-user Task Scheduler job that runs the Nova localhost watchdog at logon.
#>
$ErrorActionPreference = 'Stop'
$repo = if ($env:NOVA_REPO) { $env:NOVA_REPO } else { 'C:\Users\aalta\github\Nova' }
$watch = Join-Path $repo 'scripts\Watch-NovaLocalhost.ps1'
if (-not (Test-Path $watch)) { throw "Missing $watch" }

$taskName = 'NovaLocalhostWatchdog'
$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watch`" -IntervalSec 20"

# Remove old if present
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $ps -Argument $arg
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

# Start now
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime, LastTaskResult, NextRunTime
Write-Host "Registered and started: $taskName"
Write-Host "Log: $repo\logs\nova-localhost-watch.log"
