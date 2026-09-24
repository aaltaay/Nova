/** Times as the read says them: Eastern wall clock, 24-hour. */

const ET_HM = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
const ET_HMS = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});
const DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });

export function hhmmEt(epochSec: number | null | undefined): string {
  if (epochSec === null || epochSec === undefined || !Number.isFinite(epochSec) || epochSec <= 0) return '--:--';
  return ET_HM.format(new Date(epochSec * 1000));
}

export function hhmmssEt(epochSec: number | null | undefined): string {
  if (epochSec === null || epochSec === undefined || !Number.isFinite(epochSec) || epochSec <= 0) return '--:--:--';
  return ET_HMS.format(new Date(epochSec * 1000));
}

/** "Sep 24" for an ISO day. */
export function dayShort(isoDay: string): string {
  const t = Date.parse(`${isoDay.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(t) ? isoDay : DAY.format(new Date(t));
}
