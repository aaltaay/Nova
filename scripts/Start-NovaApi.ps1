<#
.SYNOPSIS
  Starts the Nova FastAPI backend and writes console output to a log file so a
  crash can be diagnosed after the window closes.

.DESCRIPTION
  Default is a stable process (NOVA_API_RELOAD=0). uvicorn --reload / WatchFiles
  drops :8000 mid-session and looks like "the API stopped" -- see PROBLEM_LOG
  2026-07-14, 2026-08-14, 2026-08-28. Pass -Reload only for local hot-reload.

  Default mode redirects stdout/stderr to the log file with no interactive
  console. An interactive PowerShell console + Tee-Object can freeze the
  entire API process if the window enters QuickEdit select mode (zero CPU,
  /api/health times out, UI shows API_WEDGED) -- see PROBLEM_LOG 2026-07-30.

.PARAMETER LogFile
  Relative or absolute path for the API console log.

.PARAMETER Interactive
  Opt-in: show a visible console and Tee to the log (legacy debugging path).

.PARAMETER Reload
  Opt-in: uvicorn --reload / WatchFiles. Do not use on a trading morning.
#>
param(
    [string]$LogFile = "logs\api-console.log",
    [switch]$Interactive,
    [switch]$Reload
)

$ErrorActionPreference = "Continue"

$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

$pyLauncher = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } else { "python" }

$rotateTool = Join-Path $PSScriptRoot "..\tools\rotate_log_file.py"
if (Test-Path $rotateTool) {
    $absLog = $LogFile
    if (-not [System.IO.Path]::IsPathRooted($LogFile)) {
        $absLog = Join-Path (Get-Location) $LogFile
    }
    cmd /c "$pyLauncher `"$rotateTool`" --path `"$absLog`""
}

if ($Reload) {
    $env:NOVA_API_RELOAD = "1"
} else {
    $env:NOVA_API_RELOAD = "0"
}

$reloadPrefix = if ($Reload) { "set NOVA_API_RELOAD=1 && " } else { "set NOVA_API_RELOAD=0 && " }

if ($Interactive) {
    # Merge stdout+stderr inside cmd.exe (not PowerShell) so Tee-Object writes
    # plain readable lines instead of wrapping native stderr as ErrorRecord noise.
    $cmdLine = "$reloadPrefix$pyLauncher run_api.py 2>&1"
    cmd /c $cmdLine | Tee-Object -FilePath $LogFile
} else {
    # Hidden / non-interactive: file redirection only (QuickEdit-safe).
    $cmdLine = "$reloadPrefix$pyLauncher run_api.py >> `"$LogFile`" 2>&1"
    cmd /c $cmdLine
}
