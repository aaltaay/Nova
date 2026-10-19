import { SESSION_PREMARKET_START_MIN_ET } from '../constants';

const ET_DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
});

const DAY_MS = 86_400_000;

/**
 * The desk's trading day of an instant, `YYYY-MM-DD`: it starts at the 04:00 ET premarket open, and
 * a weekend belongs to the Friday before it, so Saturday 04:00 is no rollover (the backend's
 * `market.session_key_et` and `practice.clock.session_day_start_ts` agree). The client does not know
 * NYSE holidays (the same limit as `globalBarSession`), so a holiday still reads as its own day here.
 */
export function deskTradingDay(ms: number): string {
  let day = ET_DAY.format(new Date(ms - SESSION_PREMARKET_START_MIN_ET * 60_000));
  // The ET calendar date as a UTC midnight, so the weekday is that date's, whatever this PC's zone.
  let at = Date.parse(`${day}T00:00:00Z`);
  while (new Date(at).getUTCDay() === 0 || new Date(at).getUTCDay() === 6) {
    at -= DAY_MS;
    day = new Date(at).toISOString().slice(0, 10);
  }
  return day;
}
