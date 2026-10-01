"""The API process's Windows scheduling priority: Normal CPU, I/O and memory priority, whatever started it.

A Windows process inherits its parent's I/O and memory priority, and its parent's CPU priority class
when that class is BelowNormal or Idle. Task Scheduler's default task priority (7) is BelowNormal CPU,
Low I/O priority and memory priority 2 of 5, so on 2026-10-01 the API the localhost watchdog task had
started ran at all three, and so did the IB Gateway the morning task had launched. A process started
from a below-normal shell (explorer.exe ran BelowNormal on the desk PC that day) inherits its CPU class
the same way. ``normal.raise_to_normal`` runs first in ``run_api.main`` and never lowers anything.
"""
