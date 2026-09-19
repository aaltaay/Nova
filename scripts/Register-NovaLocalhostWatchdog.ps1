#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$repo = if ($env:NOVA_REPO) { $env:NOVA_REPO } else { 'C:\Users\aalta\github\Nova' }
$watch = Join-Path $repo 'scripts\Watch-NovaLocalhost.ps1'
$taskName = 'NovaLocalhostWatchdog'
$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watch`" -IntervalSec 20"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $ps -Argument $arg
# At logon + also start whenever the machine is on: daily trigger that repeats every 1 min
# (starts watch; mutex exits duplicates immediately so this is cheap)
$tLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$tRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action `
  -Trigger @($tLogon, $tRepeat) -Settings $settings -Principal $principal -Force | Out-Null

# Launch detached watch NOW (don't rely only on task result codes)
Start-Process -FilePath $ps -ArgumentList $arg -WindowStyle Hidden
Start-Sleep 5
Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep 2
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -EA SilentlyContinue |
  Where-Object { $_.CommandLine -match 'Watch-NovaLocalhost' } |
  Select-Object ProcessId
