<# Idempotent, user-level installation. Linked worktrees never own this task. #>
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = 'NovaRepoHygiene',
    [string]$AtTime = '02:30'
)
$ErrorActionPreference = 'Stop'
try {
    $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git') -PathType Container)) {
        Write-Output 'Repo maintenance: skipped (not a main Git checkout).'
        exit 0
    }
    $runner = Join-Path $RepoRoot 'scripts\Invoke-NovaRepoHygiene.ps1'
    $tool = Join-Path $RepoRoot 'tools\repo_hygiene.py'
    if (-not (Test-Path -LiteralPath $runner) -or -not (Test-Path -LiteralPath $tool)) {
        throw 'Maintenance files are missing; synchronize the checkout first.'
    }
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    # An explicit installer time wins; ordinary startup preserves a user's schedule.
    if (-not $PSBoundParameters.ContainsKey('AtTime') -and $existing -and
        @($existing.Triggers).Count -eq 1 -and $existing.Triggers[0].DaysInterval -eq 1) {
        $AtTime = ([DateTime]$existing.Triggers[0].StartBoundary).ToString('HH:mm')
    }
    $at = [DateTime]::ParseExact($AtTime, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
    $arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        $runner + '" -RepoRoot "' + $RepoRoot + '"'
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value

    function Test-MaintenanceTask($task) {
        if ($null -eq $task -or $task.State -eq 'Disabled') { return $false }
        $actions = @($task.Actions)
        $triggers = @($task.Triggers)
        $savedUser = $task.Principal.UserId
        if ($savedUser -notmatch '^S-1-') {
            try {
                $account = New-Object Security.Principal.NTAccount($savedUser)
                $savedUser = $account.Translate([Security.Principal.SecurityIdentifier]).Value
            } catch { return $false }
        }
        return ($actions.Count -eq 1 -and $triggers.Count -eq 1 -and
            $actions[0].Execute -eq 'powershell.exe' -and
            $actions[0].Arguments -eq $arguments -and
            $actions[0].WorkingDirectory -eq $RepoRoot -and
            $triggers[0].Enabled -and $triggers[0].DaysInterval -eq 1 -and
            ([DateTime]$triggers[0].StartBoundary).ToString('HH:mm') -eq $AtTime -and
            $task.Settings.StartWhenAvailable -and
            $task.Settings.MultipleInstances -eq 'IgnoreNew' -and
            $task.Settings.RestartCount -eq 3 -and
            $task.Settings.RestartInterval -eq 'PT5M' -and
            $task.Settings.ExecutionTimeLimit -eq 'PT15M' -and
            $savedUser -eq $sid -and
            $task.Principal.LogonType -eq 'Interactive' -and
            $task.Principal.RunLevel -eq 'Limited')
    }

    if (Test-MaintenanceTask $existing) {
        Write-Output "Repo maintenance: $TaskName verified."
        exit 0
    }
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force `
        -Description 'Nova repository maintenance; results in logs/repo-hygiene.log.' | Out-Null
    if (-not (Test-MaintenanceTask (Get-ScheduledTask -TaskName $TaskName))) {
        throw 'Saved task does not match the maintenance configuration.'
    }
    Write-Output "Repo maintenance: $TaskName installed and verified at $AtTime."
    exit 0
} catch {
    Write-Warning ("Repo maintenance setup failed: " + $_.Exception.Message)
    exit 2
}
