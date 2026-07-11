<#
.SYNOPSIS
  Force-stops any process currently listening on the given local ports.

.DESCRIPTION
  Used by Run Nova.bat / Stop Nova.bat / Run Nova Desktop.bat to guarantee a
  clean "safe open" (no stale process holding the port from a previous,
  possibly crashed, session) and to provide an explicit "safe close" path.

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

foreach ($port in $portList) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { continue }

    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        if (-not $procId -or $procId -eq 0) { continue }
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { "unknown" }
        Write-Host "Nova: stopping existing process on port $port (PID $procId, $name)"
        try {
            # /T kills the whole process tree (uvicorn --reload spawns a child worker).
            Start-Process -FilePath "taskkill.exe" -ArgumentList @("/PID", "$procId", "/T", "/F") `
                -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue | Out-Null
        } catch {
            Write-Host "Nova: could not stop PID $procId ($_)"
        }
    }
}
