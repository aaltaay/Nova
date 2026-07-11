<#
.SYNOPSIS
  Starts the Nova Vite dev server and tees console output to a log file so
  a crash can be diagnosed after the window closes.
#>
param(
    [string]$LogFile = "..\backend\logs\ui-console.log"
)

$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

cmd /c "npm run dev 2>&1" | Tee-Object -FilePath $LogFile
