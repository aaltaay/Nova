#Requires -Version 5.1
param([int]$IntervalSec = 20)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'NovaLocalhost.Common.ps1')

$created = $false
try {
  $mutex = New-Object System.Threading.Mutex($false, $script:NovaMutexName, [ref]$created)
} catch {
  $mutex = $null
}
if ($mutex) {
  if (-not $mutex.WaitOne(0)) {
    Write-NovaLog 'Watchdog already running - exiting duplicate'
    exit 0
  }
}

Write-NovaLog ("Watchdog start interval={0}s repo={1}" -f $IntervalSec, $script:NovaRepo)
[void](Start-NovaLocalhostStack)

# Vite that keeps failing (e.g. node_modules missing vite) is retried less often, so the API --
# which the desk needs -- is checked every interval (2026-09-29: a failed Vite start every ~100 s
# for thirteen hours, and an API restart waited behind it). Any success resets it.
$viteFailures = 0
$viteNextTry = [datetime]::MinValue
$viteBackoffAfter = 3
$viteBackoffMin = 10

try {
  while ($true) {
    try {
      $st = Get-NovaLocalhostStatus
      if (-not $st.apiHealthy) {
        Write-NovaLog ("API unhealthy (portUp={0}) - restarting" -f $st.apiPortUp)
        [void](Start-NovaApi)
      }
      if ($st.vite) {
        $viteFailures = 0
      } elseif ((Get-Date) -ge $viteNextTry) {
        Write-NovaLog 'Vite down - restarting'
        if (Start-NovaVite) {
          $viteFailures = 0
        } else {
          $viteFailures++
          if ($viteFailures -ge $viteBackoffAfter) {
            $viteNextTry = (Get-Date).AddMinutes($viteBackoffMin)
            Write-NovaLog ("Vite failed {0} times in a row - next try in {1} min (the API is still checked every {2} s)" -f $viteFailures, $viteBackoffMin, $IntervalSec)
          }
        }
      }
    } catch {
      Write-NovaLog ("Watch loop error: {0}" -f $_.Exception.Message)
    }
    Start-Sleep -Seconds ([Math]::Max(5, $IntervalSec))
  }
} finally {
  if ($mutex) {
    try { $mutex.ReleaseMutex() } catch {}
    $mutex.Dispose()
  }
}