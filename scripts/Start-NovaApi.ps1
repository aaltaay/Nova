<#
.SYNOPSIS
  Starts the Nova FastAPI backend (dev mode, hot-reload) and writes console
  output to a log file so a crash can be diagnosed after the window closes.

.DESCRIPTION
  Default mode redirects stdout/stderr to the log file with no interactive
  console. An interactive PowerShell console + Tee-Object can freeze the
  entire API process if the window enters QuickEdit select mode (zero CPU,
  /api/health times out, UI shows API_WEDGED) -- see PROBLEM_LOG 2026-07-30.

.PARAMETER LogFile
  Relative or absolute path for the API console log.

.PARAMETER Interactive
  Opt-in: show a visible console and Tee to the log (legacy debugging path).
#>
param(
    [string]$LogFile = "logs\api-console.log",
    [switch]$Interactive
)

$ErrorActionPreference = "Continue"

$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

$pyLauncher = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } else { "python" }

# Ensure reload is on for local daily / Run Nova paths.
$env:NOVA_API_RELOAD = "1"

if ($Interactive) {
    # Merge stdout+stderr inside cmd.exe (not PowerShell) so Tee-Object writes
    # plain readable lines instead of wrapping native stderr as ErrorRecord noise.
    $cmdLine = "set NOVA_API_RELOAD=1 && $pyLauncher run_api.py 2>&1"
    cmd /c $cmdLine | Tee-Object -FilePath $LogFile
} else {
    # Hidden / non-interactive: file redirection only (QuickEdit-safe).
    $cmdLine = "set NOVA_API_RELOAD=1 && $pyLauncher run_api.py >> `"$LogFile`" 2>&1"
    cmd /c $cmdLine
}
