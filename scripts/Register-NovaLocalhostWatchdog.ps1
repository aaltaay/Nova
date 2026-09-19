#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$repo = if ($env:NOVA_REPO) { $env:NOVA_REPO } else { 'C:\Users\aalta\github\Nova' }
$watch = Join-Path $repo 'scripts\Watch-NovaLocalhost.ps1'
$taskName = 'NovaLocalhostWatchdog'
$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watch`" -IntervalSec 20"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $ps -Argument $arg
$tLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# Kick every 5 minutes for a year — mutex makes extras no-ops if watch already looping
$tRepeat = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Days 365)
$settings = New-ScheduledTaskSettingsSet `
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

# Detached long-running watch now
Start-Process -FilePath $ps -ArgumentList $arg -WindowStyle Hidden
Start-Sleep 4
Write-Host 'Task:'
Get-ScheduledTask -TaskName $taskName | Format-Table TaskName, State -AutoSize
Write-Host 'Watch processes:'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -match 'Watch-NovaLocalhost' } |
  Select-Object ProcessId | Format-Table -AutoSize
