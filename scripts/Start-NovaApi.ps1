<#
.SYNOPSIS
  Starts the Nova FastAPI backend (dev mode, hot-reload) and tees console
  output to a log file so a crash can be diagnosed after the window closes.
#>
param(
    [string]$LogFile = "logs\api-console.log"
)

$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

$pyLauncher = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } else { "python" }

# Merge stdout+stderr inside cmd.exe (not PowerShell) so Tee-Object writes
# plain readable lines instead of wrapping native stderr as ErrorRecord noise.
$cmdLine = "set NOVA_API_RELOAD=1 && $pyLauncher run_api.py 2>&1"
cmd /c $cmdLine | Tee-Object -FilePath $LogFile
