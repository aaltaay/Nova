<#
.SYNOPSIS
  Force-stops any Nova-owned process currently listening on the given local ports.

.DESCRIPTION
  Used by Run Nova.bat / Stop Nova.bat / Run Nova Desktop.bat to guarantee a
  clean "safe open" (no stale process holding the port from a previous,
  possibly crashed, session) and to provide an explicit "safe close" path.

  Verifies ownership via the process command line before killing (best
  effort — Win32_Process.CommandLine can be unavailable without elevation,
  in which case it proceeds since 8000/5173 are Nova's own dedicated dev
  ports). A process whose command line is readable and clearly is NOT Nova
  is left alone with a loud warning instead of being killed — see
  PROBLEM_LOG 2026-07-23 (arbitrary port-kill was part of the restart-race
  root cause).

.PARAMETER Ports
  Comma-separated TCP ports to check, e.g. "8000,5173" (default: Nova's API
  port 8000 and Vite dev port 5173). Passed as a single string because
  command-line invocation from .bat files does not reliably preserve
  PowerShell array syntax across the process boundary.
#>
param(
    [string]$Ports = "8000,5173"
)

$portList = $Ports -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ } | ForEach-Object { [int]$_ }

function Test-NovaOwnedProcess {
    <# Returns $true/$false when the command line was readable, $null when
       ownership could not be verified (no permission / process gone). #>
    param([int]$ProcId)
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcId" -ErrorAction Stop).CommandLine
    } catch {
        return $null
    }
    if (-not $cmd) { return $null }
    return ($cmd -match "run_api\.py" -or $cmd -match "uvicorn" -or $cmd -match "vite")
}

foreach ($port in $portList) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { continue }

    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        if (-not $procId -or $procId -eq 0) { continue }
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { "unknown" }
        $owned = Test-NovaOwnedProcess -ProcId $procId

        if ($owned -eq $false) {
            Write-Host "Nova: port $port is held by PID $procId ($name), which does not look like a Nova process — leaving it alone. Free this port manually if it is blocking Nova."
            continue
        }
        if ($null -eq $owned) {
            Write-Host "Nova: stopping process on port $port (PID $procId, $name) — ownership could not be verified, proceeding (dedicated Nova dev port)"
        } else {
            Write-Host "Nova: stopping existing Nova process on port $port (PID $procId, $name)"
        }
        try {
            # /T kills the whole process tree (uvicorn --reload spawns a child worker).
            Start-Process -FilePath "taskkill.exe" -ArgumentList @("/PID", "$procId", "/T", "/F") `
                -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue | Out-Null
        } catch {
            Write-Host "Nova: could not stop PID $procId ($_)"
        }
    }
}
