#Requires -Version 5.1
<#
.SYNOPSIS
  Normal CPU, I/O and memory priority for Nova's trading path.

.DESCRIPTION
  A Windows process inherits its parent's I/O and memory priority, and its
  parent's CPU priority class when that class is BelowNormal or Idle. Task
  Scheduler starts a task at its Priority setting, and the default (7) is
  BelowNormal CPU, Low I/O priority and memory priority 2 (of 5). On
  2026-10-01 the watchdog's API and Vite ran that way, and so did the IB
  Gateway: NovaDailyStart had started its IBC loop at logon on 09-28, and IBC
  relaunches every Gateway from that loop. Setting PriorityClass alone leaves
  the I/O and memory priority low.

  Set-NovaNormalPriority raises a process (this one by default) to Normal on
  all three and never lowers one, so whatever it starts afterwards inherits
  Normal; a raise reaches the threads already running. It never throws: it
  returns a line for the caller's log. scripts/Repair-NovaPriority.ps1 uses it
  on the processes already running.

  ASCII-only: dot-sourced by scripts that powershell.exe 5.1 runs under Task
  Scheduler (test_scripts_ascii.py).
#>

$script:NovaPriorityNativeError = $null

function Initialize-NovaPriorityNative {
  if ('NovaProcessPriorityNative' -as [type]) { return $true }
  if ($script:NovaPriorityNativeError) { return $false }
  try {
    Add-Type -ErrorAction Stop -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class NovaProcessPriorityNative {
  const uint QueryLimited = 0x1000;     // PROCESS_QUERY_LIMITED_INFORMATION
  const uint SetInformation = 0x0200;   // PROCESS_SET_INFORMATION
  const int IoPriorityClass = 33;       // ProcessIoPriority (NtQuery/SetInformationProcess)
  const int MemoryPriorityClass = 0;    // ProcessMemoryPriority (Get/SetProcessInformation)
  public const uint Idle = 0x40;
  public const uint BelowNormal = 0x4000;
  public const uint Normal = 0x20;
  public const int IoNormal = 2;        // 0 very low, 1 low, 2 normal, 3 high
  public const int MemoryNormal = 5;    // 1 very low .. 5 normal

  [DllImport("kernel32.dll", SetLastError = true)]
  static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
  [DllImport("kernel32.dll")]
  static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern uint GetPriorityClass(IntPtr handle);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool SetPriorityClass(IntPtr handle, uint priorityClass);
  [DllImport("ntdll.dll")]
  static extern int NtQueryInformationProcess(IntPtr handle, int infoClass, ref int info, int length, IntPtr returnLength);
  [DllImport("ntdll.dll")]
  static extern int NtSetInformationProcess(IntPtr handle, int infoClass, ref int info, int length);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool GetProcessInformation(IntPtr handle, int infoClass, ref int info, int size);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool SetProcessInformation(IntPtr handle, int infoClass, ref int info, int size);

  // { CPU priority class, I/O priority, memory priority }; -1 where Windows would not say.
  public static long[] Read(int pid) {
    IntPtr handle = OpenProcess(QueryLimited, false, pid);
    if (handle == IntPtr.Zero) return new long[] { -1, -1, -1 };
    try {
      uint cls = GetPriorityClass(handle);
      int io = 0;
      int memory = 0;
      return new long[] {
        cls == 0 ? -1 : (long)cls,
        NtQueryInformationProcess(handle, IoPriorityClass, ref io, 4, IntPtr.Zero) == 0 ? io : -1,
        GetProcessInformation(handle, MemoryPriorityClass, ref memory, 4) ? memory : -1
      };
    } finally {
      CloseHandle(handle);
    }
  }

  // Raises a BelowNormal or Idle CPU class, and an I/O or memory priority under
  // normal, to Normal; never lowers one. Returns what Windows refused, or null.
  public static string Raise(int pid) {
    IntPtr handle = OpenProcess(QueryLimited | SetInformation, false, pid);
    if (handle == IntPtr.Zero) return "cannot open the process (Win32 error " + Marshal.GetLastWin32Error() + ")";
    try {
      List<string> refused = new List<string>();
      uint cls = GetPriorityClass(handle);
      if ((cls == Idle || cls == BelowNormal) && !SetPriorityClass(handle, Normal)) {
        refused.Add("CPU class (Win32 error " + Marshal.GetLastWin32Error() + ")");
      }
      int io = 0;
      if (NtQueryInformationProcess(handle, IoPriorityClass, ref io, 4, IntPtr.Zero) == 0 && io < IoNormal) {
        int target = IoNormal;
        int status = NtSetInformationProcess(handle, IoPriorityClass, ref target, 4);
        if (status != 0) refused.Add("I/O priority (NTSTATUS 0x" + status.ToString("X8") + ")");
      }
      int memory = 0;
      if (GetProcessInformation(handle, MemoryPriorityClass, ref memory, 4) && memory < MemoryNormal) {
        int target = MemoryNormal;
        if (!SetProcessInformation(handle, MemoryPriorityClass, ref target, 4)) {
          refused.Add("memory priority (Win32 error " + Marshal.GetLastWin32Error() + ")");
        }
      }
      return refused.Count == 0 ? null : string.Join("; ", refused.ToArray());
    } finally {
      CloseHandle(handle);
    }
  }
}
'@
    return $true
  } catch {
    $script:NovaPriorityNativeError = $_.Exception.Message
    return $false
  }
}

function Format-NovaPriority([long[]]$Values) {
  $class = switch ($Values[0]) {
    0x40 { 'Idle' }
    0x4000 { 'BelowNormal' }
    0x20 { 'Normal' }
    0x8000 { 'AboveNormal' }
    0x80 { 'High' }
    0x100 { 'RealTime' }
    -1 { 'unknown' }
    default { '0x{0:X}' -f $Values[0] }
  }
  $io = switch ($Values[1]) {
    0 { 'VeryLow' }
    1 { 'Low' }
    2 { 'Normal' }
    3 { 'High' }
    4 { 'Critical' }
    default { 'unknown' }
  }
  $memory = if ($Values[2] -ge 0) { "$($Values[2])/5" } else { 'unknown' }
  return "CPU $class, I/O $io, memory $memory"
}

function Test-NovaPriorityLow([long[]]$Values) {
  return ($Values[0] -eq 0x40 -or $Values[0] -eq 0x4000 -or
    ($Values[1] -ge 0 -and $Values[1] -lt 2) -or ($Values[2] -ge 0 -and $Values[2] -lt 5))
}

function Test-NovaPriorityUnknown([long[]]$Values) {
  return ($Values[0] -eq -1 -and $Values[1] -eq -1 -and $Values[2] -eq -1)
}

# { CPU class, I/O priority, memory priority } of a process, -1 where Windows would not
# say; $null when the native calls cannot load.
function Get-NovaProcessPriority {
  param([int]$ProcessId = $PID)
  if (-not (Initialize-NovaPriorityNative)) { return $null }
  return [NovaProcessPriorityNative]::Read($ProcessId)
}

# Returns Text (one line for a log), Changed (it raised something) and Ok (it now reads
# no lower than Normal on all three; false when it could not be read or raised).
function Set-NovaNormalPriority {
  param([int]$ProcessId = $PID)
  $result = [pscustomobject]@{ ProcessId = $ProcessId; Text = ''; Changed = $false; Ok = $false }
  try {
    if (-not (Initialize-NovaPriorityNative)) {
      $result.Text = "pid $ProcessId priority unchanged: $($script:NovaPriorityNativeError)"
      return $result
    }
    $before = [NovaProcessPriorityNative]::Read($ProcessId)
    if (Test-NovaPriorityUnknown $before) {
      $result.Text = "pid $ProcessId priority unknown: Windows would not open the process"
      return $result
    }
    if (-not (Test-NovaPriorityLow $before)) {
      $result.Text = "pid $ProcessId priority $(Format-NovaPriority $before)"
      $result.Ok = $true
      return $result
    }
    $refused = [NovaProcessPriorityNative]::Raise($ProcessId)
    $after = [NovaProcessPriorityNative]::Read($ProcessId)
    $result.Changed = $true
    $result.Ok = -not (Test-NovaPriorityLow $after) -and -not (Test-NovaPriorityUnknown $after)
    $result.Text = "pid $ProcessId priority raised $(Format-NovaPriority $before) -> $(Format-NovaPriority $after)"
    if ($refused) { $result.Text += " (Windows refused $refused)" }
    return $result
  } catch {
    $result.Text = "pid $ProcessId priority unchanged: $($_.Exception.Message)"
    return $result
  }
}
