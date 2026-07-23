<#
.SYNOPSIS
  Register (or remove) a Windows Scheduled Task that runs Start-NovaDaily.ps1.

.DESCRIPTION
  Runs in the interactive user session so titled API/UI windows appear.
  Does not store IBKR passwords. Gateway login uses your local IBC config.

.PARAMETER Trigger
  Daily     - once per day at -AtTime (default 06:00)
  AtLogon   - when you sign into Windows
  Both      - Daily + AtLogon (default; Start-NovaDaily is idempotent)

.PARAMETER AtTime
  Local clock time for the Daily trigger (default 06:00).

.PARAMETER TaskName
  Scheduled task name (default NovaDailyStart).

.PARAMETER Unregister
  Remove the task instead of creating/updating it.

.PARAMETER SkipGateway
  Pass -SkipGateway through to Start-NovaDaily.ps1.

.PARAMETER SkipBrowser
  Pass -SkipBrowser through to Start-NovaDaily.ps1.

.EXAMPLE
  .\scripts\Install-NovaDailyTask.ps1
  .\scripts\Install-NovaDailyTask.ps1 -Trigger Daily -AtTime 06:00
  .\scripts\Install-NovaDailyTask.ps1 -Trigger AtLogon
  .\scripts\Install-NovaDailyTask.ps1 -Unregister
#>
param(
    [ValidateSet("Daily", "AtLogon", "Both")]
    [string]$Trigger = "Both",
    [string]$AtTime = "06:00",
    [string]$TaskName = "NovaDailyStart",
    [switch]$Unregister,
    [switch]$SkipGateway,
    [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $repoRoot "scripts\Start-NovaDaily.ps1"

if (-not (Test-Path $startScript)) {
    throw "Missing $startScript"
}

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "No scheduled task named '$TaskName' - nothing to remove." -ForegroundColor Yellow
    }
    return
}

$argParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Normal",
    "-File", $startScript,
    "-RepoRoot", $repoRoot
)
if ($SkipGateway) { $argParts += "-SkipGateway" }
if ($SkipBrowser) { $argParts += "-SkipBrowser" }

# Quote paths for the scheduled-task command line.
$argument = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$startScript`" -RepoRoot `"$repoRoot`""
if ($SkipGateway) { $argument += " -SkipGateway" }
if ($SkipBrowser) { $argument += " -SkipBrowser" }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $argument `
    -WorkingDirectory $repoRoot

$triggers = @()
if ($Trigger -eq "Daily" -or $Trigger -eq "Both") {
    try {
        $parsed = Get-Date $AtTime
    } catch {
        throw "Invalid -AtTime '$AtTime'. Use something like 06:00 or 6:00AM."
    }
    $triggers += New-ScheduledTaskTrigger -Daily -At $parsed
}
if ($Trigger -eq "AtLogon" -or $Trigger -eq "Both") {
    $triggers += New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

try {
    $settings.WakeToRun = $true
} catch {
    # older PowerShell builds may not expose the property the same way
}

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Description "Start IB Gateway (IBC) + Nova API/UI. Idempotent. See scripts/Start-NovaDaily.ps1." | Out-Null

$triggerDesc = $Trigger
if ($Trigger -ne "AtLogon") {
    $triggerDesc = "$Trigger at $AtTime local"
}

Write-Host ""
Write-Host "Registered scheduled task '$TaskName'" -ForegroundColor Green
Write-Host "  Trigger : $triggerDesc"
Write-Host "  Script  : $startScript"
Write-Host "  Repo    : $repoRoot"
Write-Host ""
Write-Host "Test now:" -ForegroundColor Cyan
Write-Host ("  schtasks /Run /TN " + $TaskName)
Write-Host ("  OR:  powershell -NoProfile -ExecutionPolicy Bypass -File " + $startScript)
Write-Host ""
Write-Host "Remove later:" -ForegroundColor Cyan
Write-Host "  .\scripts\Install-NovaDailyTask.ps1 -Unregister"
Write-Host ""
Write-Host "Note: if the PC is asleep at $AtTime, enable wake timers in Windows" -ForegroundColor Yellow
Write-Host "power settings, or rely on the AtLogon trigger after you unlock." -ForegroundColor Yellow
