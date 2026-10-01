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
# Before anything starts: the API and Vite inherit this process's priority (2026-10-01).
Set-NovaLauncherPriority -Always
[void](Start-NovaLocalhostStack)

# Vite that keeps failing (e.g. node_modules missing vite) is retried less often, so the API --
# which the desk needs -- is checked every interval (2026-09-29: a failed Vite start every ~100 s
# for thirteen hours, and an API restart waited behind it). Any success resets it.
$viteFailures = 0
$viteNextTry = [datetime]::MinValue
$viteBackoffAfter = 3
$viteBackoffMin = 10

# PowerShell never reads a running script again, so a watchdog started before a fix keeps the
# old code (2026-09-30: running since 09-28 20:18, it held a failing Vite start ~75 s at a time,
# 566 times that day, and a backend restart waited 90 s behind it -- the fix above had merged on
# 09-29). When any of its scripts changes on disk and they all parse, it starts itself again and exits.
$scriptFiles = @(
  $PSCommandPath,
  (Join-Path $PSScriptRoot 'NovaLocalhost.Common.ps1'),
  (Join-Path $PSScriptRoot 'NovaProcessPriority.ps1')
)
function Get-NovaScriptStamp {
  ($scriptFiles | ForEach-Object { (Get-Item -LiteralPath $_ -ErrorAction SilentlyContinue).LastWriteTimeUtc.Ticks }) -join ','
}
function Test-NovaScriptsParse {
  foreach ($file in $scriptFiles) {
    # A pull writes the files one at a time: a missing one is not ready yet.
    if (-not (Test-Path -LiteralPath $file)) {
      Write-NovaLog ("Watchdog script changed but {0} is missing - keeping the running code" -f $file)
      return $false
    }
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$errors)
    if ($errors -and $errors.Count) {
      Write-NovaLog ("Watchdog script changed but does not parse ({0}: {1}) - keeping the running code" -f $file, $errors[0].Message)
      return $false
    }
  }
  return $true
}
$scriptStamp = Get-NovaScriptStamp
$relaunch = $false

try {
  while ($true) {
    $stamp = Get-NovaScriptStamp
    if ($stamp -ne $scriptStamp) {
      $scriptStamp = $stamp
      if (Test-NovaScriptsParse) {
        Write-NovaLog 'Watchdog scripts changed on disk - starting the new code'
        $relaunch = $true
        break
      }
    }
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

# The mutex is released first, so the new watchdog is not turned away as a duplicate.
if ($relaunch) {
  Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', "`"$PSCommandPath`"", '-IntervalSec', "$IntervalSec"
  ) | Out-Null
}