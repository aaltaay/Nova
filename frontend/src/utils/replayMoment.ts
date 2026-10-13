/**
 * How the quote panel names a replayed moment on a Sim replay desk (operator report, 2026-10-12):
 * "Jul 15 07:20 ET". Every card that shows a past day's fact says which moment it is from.
 */
const DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });
const CLOCK_ET = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
});

/** "Jul 15" from "2026-07-15"; the input as given when it is not a date. */
export function replayDayLabel(sessionDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(sessionDate);
  if (!m) return sessionDate;
  return DAY.format(new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12)));
}

/** "07:20" in New York from epoch seconds. */
export function replayClockEt(ts: number): string {
  return CLOCK_ET.format(new Date(ts * 1000));
}

/** "Jul 15 07:20 ET". */
export function replayMomentLabel(sessionDate: string, ts: number): string {
  return `${replayDayLabel(sessionDate)} ${replayClockEt(ts)} ET`;
}
