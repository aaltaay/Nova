#Requires -Version 5.1
<#
  Is a local TCP port open? Shared by the daily start, the morning check, the dev launcher
  and the localhost watchdog.

  Windows' own listing (Get-NetTCPConnection -State Listen, netstat) can show no row for a
  port that accepts connections: IB Gateway's 4001 on every run from 2026-10-30 to 11-15,
  while Nova was connected through it (#14). Measured on that PC (Windows build 26300): a
  listener bound to 127.0.0.1 has no netstat row and a blank State. So a "no" from the listing is only believed
  after a real connection also fails. A "yes" from the listing is believed as it is.
  ASCII-only: powershell.exe 5.1 runs it under Task Scheduler.
#>

function Test-NovaPortListed([int]$Port) {
  try {
    $hit = netstat -ano 2>$null | Select-String -Pattern (":$Port\s+.*LISTENING") | Select-Object -First 1
    if ($hit) { return $true }
  } catch { }
  try {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -First 1)
  } catch {
    return $false
  }
}

function Test-NovaPortConnect([int]$Port, [int]$TimeoutMs = 400) {
  # Opens a connection and closes it at once; sends nothing.
  foreach ($address in @('127.0.0.1', '::1')) {
    $client = $null
    try {
      $ip = [System.Net.IPAddress]::Parse($address)
      $client = New-Object System.Net.Sockets.TcpClient($ip.AddressFamily)
      $pending = $client.BeginConnect($ip, $Port, $null, $null)
      if ($pending.AsyncWaitHandle.WaitOne($TimeoutMs) -and $client.Connected) { return $true }
    } catch {
      # refused, or no such address family on this PC: not open on this address
    } finally {
      if ($client) { $client.Close() }
    }
  }
  return $false
}

function Get-NovaPortProof([int]$Port) {
  # 'listing' = Windows lists it; 'connect' = only a connection proved it; '' = closed.
  if (Test-NovaPortListed $Port) { return 'listing' }
  if (Test-NovaPortConnect $Port) { return 'connect' }
  return ''
}

function Test-NovaPortOpen([int]$Port) {
  return [bool](Get-NovaPortProof $Port)
}
