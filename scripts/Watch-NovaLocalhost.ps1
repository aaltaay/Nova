#Requires -Version 5.1
param([int]$IntervalSec = 20)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'NovaLocalhost.Common.ps1')

# Single instance — Task Scheduler + manual start must not double-run.
$created = $false
try {
  $mutex = New-Object System.Threading.Mutex($false, $script:NovaMutexName, [ref]$created)
} catch {
  $mutex = $null
  $created = $true
}
if ($mutex -and -not $mutex.WaitOne(0)) {
  Write-NovaLog 'Watchdog already running — exiting duplicate'
  exit 0
}

Write-NovaLog "Watchdog start interval=${IntervalSec}s repo=$($script:NovaRepo)"
[void](Start-NovaLocalhostStack)

try {
  while ($true) {
    try {
      $st = Get-NovaLocalhostStatus
      if (-not $st.apiHealthy) {
        Write-NovaLog ("API unhealthy (portUp={0}) — restarting" -f $st.apiPortUp)
        [void](Start-NovaApi)
      }
      if (-not $st.vite) {
        Write-NovaLog 'Vite down — restarting'
        [void](Start-NovaVite)
      }
    } catch {
      Write-NovaLog ("Watch loop error: {0}" -f $_.Exception.Message)
    }
    Start-Sleep -Seconds ([Math]::Max(5, $IntervalSec))
  }
} finally {
  if ($mutex) { try { $mutex.ReleaseMutex() } catch {}; $mutex.Dispose() }
}
