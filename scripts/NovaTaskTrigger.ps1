#Requires -Version 5.1
<#
  A daily Task Scheduler trigger that keeps its wall-clock time across daylight saving.

  New-ScheduledTaskTrigger -Daily -At writes the start with the UTC offset of the day it was
  made ("03:40:00-04:00"). Task Scheduler then holds that instant in UTC, so after the clocks
  change the task runs an hour off: registered in summer for 03:40 and 03:55, NovaDailyStart
  and NovaMorningCheck ran at 02:40 and 02:55 from 2026-11-01 (#14). A start written with no
  offset is local time, and follows the clock.
  ASCII-only: powershell.exe 5.1 runs it under Task Scheduler.
#>

function New-NovaDailyTrigger([DateTime]$At) {
  $trigger = New-ScheduledTaskTrigger -Daily -At $At
  $trigger.StartBoundary = Get-Date -Date $At -Format "yyyy-MM-dd'T'HH:mm:ss"
  return $trigger
}

function Test-NovaTriggerFollowsClock($Trigger) {
  # False for a start that carries a UTC offset or Z: that one drifts at the clock change.
  return ([string]$Trigger.StartBoundary -match 'T\d{2}:\d{2}:\d{2}(\.\d+)?$')
}
