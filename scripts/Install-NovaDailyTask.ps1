<#
.SYNOPSIS
  Register (or remove) a Windows Scheduled Task that runs Start-NovaDaily.ps1.

.DESCRIPTION
  Runs in the interactive user session so titled API/UI windows appear.
  Does not store IBKR passwords. Gateway login uses your local IBC config.

.PARAMETER Trigger
  Daily     - once per day at -AtTime (default 06:00) plus -PremarketAtTime (default 03:40)
  AtLogon   - when you sign into Windows
  Both      - Daily + Premarket + AtLogon + session unlock (default; wake from sleep)

.PARAMETER AtTime
  Local clock time for the backstop Daily trigger (default 06:00).

.PARAMETER PremarketAtTime
  Local clock time for the pre-04:00 ET start (default 03:40). Machine should be ET.
  Pass empty string to skip this extra trigger.

.PARAMETER MorningCheckAtTime
  Local clock time for NovaMorningCheck (default 03:55). Empty string skips it.

.PARAMETER RepoHygieneAtTime
  Local clock time for NovaRepoHygiene (default 02:30). Runs
  `py -3 tools/repo_hygiene.py fix` (safe class only: merged local branches,
  stale worktrees, orphan remote refs) and appends to logs/repo-hygiene.log.
  Empty string skips it.

.PARAMETER TaskName
  Scheduled task name (default NovaDailyStart).

.PARAMETER Unregister
  Remove the daily-start task and NovaMorningCheck.

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
    [string]$PremarketAtTime = "03:40",
    [string]$MorningCheckAtTime = "03:55",
    [string]$RepoHygieneAtTime = "02:30",
    [string]$TaskName = "NovaDailyStart",
    [string]$MorningCheckTaskName = "NovaMorningCheck",
    [string]$RepoHygieneTaskName = "NovaRepoHygiene",
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
    foreach ($name in @($TaskName, $MorningCheckTaskName, $RepoHygieneTaskName)) {
        $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "Removed scheduled task '$name'." -ForegroundColor Green
        } else {
            Write-Host "No scheduled task named '$name' - nothing to remove." -ForegroundColor Yellow
        }
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
    if ($PremarketAtTime) {
        try {
            $preParsed = Get-Date $PremarketAtTime
        } catch {
            throw "Invalid -PremarketAtTime '$PremarketAtTime'. Use something like 03:40."
        }
        $triggers += New-ScheduledTaskTrigger -Daily -At $preParsed
    }
}
if ($Trigger -eq "AtLogon" -or $Trigger -eq "Both") {
    $triggers += New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
}
# Session unlock = wake from sleep / lock screen (AtLogon alone misses this).
# TASK_SESSION_UNLOCK = 8. Idempotent Start-NovaDaily skips healthy API/UI.
if ($Trigger -eq "Both") {
    $unlockUser = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
    try {
        $unlockClass = Get-CimClass -ClassName MSFT_TaskSessionStateChangeTrigger `
            -Namespace Root/Microsoft/Windows/TaskScheduler
        $triggers += New-CimInstance -CimClass $unlockClass -ClientOnly -Property @{
            Enabled     = $true
            StateChange = [uint32]8
            UserId      = $unlockUser
        }
    } catch {
        Write-Host "Could not add session-unlock trigger (wake-from-sleep): $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Daily + AtLogon still registered." -ForegroundColor Yellow
    }
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
if ($PremarketAtTime -and ($Trigger -eq "Daily" -or $Trigger -eq "Both")) {
    Write-Host "  Premarket start : $PremarketAtTime local (before 04:00 ET gappers window)"
}
Write-Host "  Script  : $startScript"
Write-Host "  Repo    : $repoRoot"
Write-Host ""

$checkScript = Join-Path $repoRoot "scripts\Invoke-NovaMorningCheck.ps1"
if ($MorningCheckAtTime -and (Test-Path $checkScript)) {
    try {
        $checkParsed = Get-Date $MorningCheckAtTime
    } catch {
        throw "Invalid -MorningCheckAtTime '$MorningCheckAtTime'. Use something like 03:55."
    }
    $checkArg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$checkScript`" -RepoRoot `"$repoRoot`""
    $checkAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $checkArg `
        -WorkingDirectory $repoRoot
    $checkTrigger = New-ScheduledTaskTrigger -Daily -At $checkParsed
    $existingCheck = Get-ScheduledTask -TaskName $MorningCheckTaskName -ErrorAction SilentlyContinue
    if ($existingCheck) {
        Unregister-ScheduledTask -TaskName $MorningCheckTaskName -Confirm:$false
    }
    Register-ScheduledTask `
        -TaskName $MorningCheckTaskName `
        -Action $checkAction `
        -Trigger $checkTrigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Nova pre-open self-check. Alerts Discord/Telegram on a failed leg. See scripts/Invoke-NovaMorningCheck.ps1." | Out-Null
    Write-Host "Registered scheduled task '$MorningCheckTaskName' at $MorningCheckAtTime local" -ForegroundColor Green
} elseif ($MorningCheckAtTime) {
    Write-Host "Morning check script missing: $checkScript" -ForegroundColor Yellow
}

# Share the startup installer; preserve cleanup exit codes in Task Scheduler.
if ($RepoHygieneAtTime) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `
        (Join-Path $PSScriptRoot 'Ensure-NovaMaintenanceTask.ps1') `
        -RepoRoot $repoRoot -TaskName $RepoHygieneTaskName -AtTime $RepoHygieneAtTime
    if ($LASTEXITCODE -ne 0) { throw 'Repo maintenance task setup failed.' }
}

Write-Host ""
Write-Host "Test now:" -ForegroundColor Cyan
Write-Host ("  schtasks /Run /TN " + $TaskName)
Write-Host ("  schtasks /Run /TN " + $MorningCheckTaskName)
Write-Host ("  schtasks /Run /TN " + $RepoHygieneTaskName)
Write-Host ("  OR:  powershell -NoProfile -ExecutionPolicy Bypass -File " + $startScript)
Write-Host ("  OR:  powershell -NoProfile -ExecutionPolicy Bypass -File " + $checkScript)
Write-Host ""
Write-Host "Remove later:" -ForegroundColor Cyan
Write-Host "  .\scripts\Install-NovaDailyTask.ps1 -Unregister"
Write-Host ""
Write-Host "Note: if the PC is asleep at $PremarketAtTime / $AtTime, enable wake timers in Windows" -ForegroundColor Yellow
Write-Host "power settings. Default Both also runs on session unlock (wake/lock)." -ForegroundColor Yellow
Write-Host "Configure a Discord/Telegram channel in Nova Settings so a failed morning check is loud." -ForegroundColor Yellow
