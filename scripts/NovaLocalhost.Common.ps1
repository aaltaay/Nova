#Requires -Version 5.1
<#
  Nova localhost helpers - API :8000 + Vite :5173.
  Defenses for every breakage we hit on the trading bench:
  - intentional Stop-Process after code updates
  - Vite/npm PATH missing under Task Scheduler
  - NetTCPIP Get-NetTCPConnection failures → netstat fallback
  - missing .env / NOVA_SIM_CAPTURE_DIR
  - API listen but unhealthy (HTTP probe)
  - duplicate starts (port check first)
  - py launcher vs python
#>
$ErrorActionPreference = 'Continue'

$script:NovaRepo = if ($env:NOVA_REPO) { $env:NOVA_REPO } else { 'C:\Users\aalta\github\Nova' }
$script:NovaApiPort = 8000
$script:NovaVitePort = 5173
$script:NovaCaptureRoot = if ($env:NOVA_SIM_CAPTURE_DIR) { $env:NOVA_SIM_CAPTURE_DIR } else { 'F:\Nova\sim_capture' }
$script:NovaLogDir = Join-Path $script:NovaRepo 'logs'
$script:NovaWatchLog = Join-Path $script:NovaLogDir 'nova-localhost-watch.log'
$script:NovaMutexName = 'Local\NovaLocalhostWatchdog'

function Write-NovaLog([string]$Message) {
  try {
    New-Item -ItemType Directory -Force -Path $script:NovaLogDir | Out-Null
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Message
    Add-Content -Path $script:NovaWatchLog -Value $line -Encoding utf8
  } catch {}
}

function Test-NovaPort([int]$Port) {
  # Prefer netstat - Get-NetTCPConnection often fails under limited/module-load contexts.
  try {
    $hit = netstat -ano 2>$null | Select-String -Pattern (":$Port\s+.*LISTENING") | Select-Object -First 1
    if ($hit) { return $true }
  } catch {}
  try {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -First 1
    return [bool]$c
  } catch {
    return $false
  }
}

function Test-NovaApiHealthy {
  if (-not (Test-NovaPort $script:NovaApiPort)) { return $false }
  try {
    # Soft probe - any HTTP response from the API socket counts as alive.
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$($script:NovaApiPort)/docs" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    return $true
  } catch {
    # 401/403/404 still means the process is serving.
    $msg = $_.Exception.Message
    if ($msg -match '401|403|404|400|422') { return $true }
    return $false
  }
}

function Import-NovaEnv {
  $envFile = Join-Path $script:NovaRepo '.env'
  if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
      if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $name = $Matches[1]
        $val = $Matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$name" -Value $val
      }
    }
  }
  $env:NOVA_SIM_CAPTURE_DIR = $script:NovaCaptureRoot
  # Ensure common Node path for Task Scheduler sessions
  $nodeDir = 'C:\Program Files\nodejs'
  if (Test-Path $nodeDir) {
    if ($env:Path -notlike "*$nodeDir*") {
      $env:Path = "$nodeDir;$env:Path"
    }
  }
}

function Get-NovaPy {
  $py = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
  if ($py) { return @{ Exe = $py; ArgsPrefix = @('-3') } }
  $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
  if ($python) { return @{ Exe = $python; ArgsPrefix = @() } }
  return $null
}

function Get-NovaNpm {
  $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
  if ($npm) { return $npm }
  $fallback = 'C:\Program Files\nodejs\npm.cmd'
  if (Test-Path $fallback) { return $fallback }
  return $null
}

function Start-NovaApi {
  if (Test-NovaApiHealthy) {
    Write-NovaLog "API healthy on $($script:NovaApiPort)"
    return $true
  }
  if (Test-NovaPort $script:NovaApiPort) {
    Write-NovaLog "API port up but unhealthy - leaving process (will retry health next loop)"
    return $false
  }
  Import-NovaEnv
  $launcher = Get-NovaPy
  if (-not $launcher) {
    Write-NovaLog "API start FAILED: py/python not found"
    return $false
  }
  $backend = Join-Path $script:NovaRepo 'backend'
  $out = Join-Path $script:NovaLogDir 'api-watch.out.log'
  $err = Join-Path $script:NovaLogDir 'api-watch.err.log'
  $args = @($launcher.ArgsPrefix) + @('run_api.py')
  Write-NovaLog "Starting API $($launcher.Exe) $args cwd=$backend"
  Start-Process -FilePath $launcher.Exe -ArgumentList $args `
    -WorkingDirectory $backend -WindowStyle Hidden `
    -RedirectStandardOutput $out -RedirectStandardError $err | Out-Null
  for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    if (Test-NovaApiHealthy) {
      Write-NovaLog "API healthy on $($script:NovaApiPort)"
      return $true
    }
  }
  Write-NovaLog "API FAILED health on $($script:NovaApiPort) - see $err"
  return $false
}

function Start-NovaVite {
  if (Test-NovaPort $script:NovaVitePort) {
    Write-NovaLog "Vite already listening on $($script:NovaVitePort)"
    return $true
  }
  Import-NovaEnv
  $npm = Get-NovaNpm
  if (-not $npm) {
    Write-NovaLog "Vite start FAILED: npm.cmd not found"
    return $false
  }
  $frontend = Join-Path $script:NovaRepo 'frontend'
  $out = Join-Path $script:NovaLogDir 'vite-watch.out.log'
  $err = Join-Path $script:NovaLogDir 'vite-watch.err.log'
  Write-NovaLog "Starting Vite $npm cwd=$frontend"
  Start-Process -FilePath $npm -ArgumentList @('run','dev','--','--host','127.0.0.1','--port',"$($script:NovaVitePort)") `
    -WorkingDirectory $frontend -WindowStyle Hidden `
    -RedirectStandardOutput $out -RedirectStandardError $err | Out-Null
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if (Test-NovaPort $script:NovaVitePort) {
      Write-NovaLog "Vite up on $($script:NovaVitePort)"
      return $true
    }
  }
  Write-NovaLog "Vite FAILED to listen on $($script:NovaVitePort) - see $err"
  return $false
}

function Start-NovaLocalhostStack {
  Import-NovaEnv
  $apiOk = Start-NovaApi
  $viteOk = Start-NovaVite
  return ($apiOk -and $viteOk)
}

function Get-NovaLocalhostStatus {
  [pscustomobject]@{
    apiPortUp = Test-NovaPort $script:NovaApiPort
    apiHealthy = Test-NovaApiHealthy
    vite = Test-NovaPort $script:NovaVitePort
    apiPort = $script:NovaApiPort
    vitePort = $script:NovaVitePort
    repo = $script:NovaRepo
  }
}

