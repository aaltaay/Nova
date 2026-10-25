/** The Market page's number words: signed percents, prices, counts and ET times. Unknown is "--", never 0. */

const DASH = '--';
const MINUS = '−';

export function signedPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const body = Math.abs(v).toFixed(digits);
  return `${v > 0 ? '+' : v < 0 ? MINUS : ''}${body}%`;
}

export function signedNum(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const body = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${v > 0 ? '+' : v < 0 ? MINUS : ''}${body}`;
}

export function signedPts(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? DASH : `${signedNum(v, 2)} pt`;
}

/** A price with the digits its size needs: 47,215 / 6,842.50 / 15.84 / 4.12. */
export function price(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const digits = Math.abs(v) >= 10_000 ? 0 : 2;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function count(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? DASH : Math.round(v).toLocaleString('en-US');
}

export function shares(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)} B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)} M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)} K`;
  return String(Math.round(v));
}

/** Dollars in a few characters: "$1.2B" / "$412M" / "$85K". */
export function money(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${Math.round(v / 1e6)}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3)}K`;
  return `$${Math.round(v)}`;
}

/** "09:41" on the ET clock. */
export function etTime(ts: number | null | undefined): string {
  if (ts == null) return DASH;
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/** "Tue 08:30" on the ET clock, or "08:30" when it is today. */
export function etWhen(ts: number, nowSec: number): string {
  const opts: Intl.DateTimeFormatOptions = { timeZone: 'America/New_York' };
  const day = (t: number) => new Date(t * 1000).toLocaleDateString('en-US', { ...opts, weekday: 'short' });
  const same =
    new Date(ts * 1000).toLocaleDateString('en-US', opts) === new Date(nowSec * 1000).toLocaleDateString('en-US', opts);
  return same ? etTime(ts) : `${day(ts)} ${etTime(ts)}`;
}

/** "6 h 08 m" / "8 m" until a time. */
export function until(seconds: number): string {
  const m = Math.max(0, Math.round(seconds / 60));
  const h = Math.floor(m / 60);
  return h > 0 ? `${h} h ${String(m % 60).padStart(2, '0')} m` : `${m} m`;
}

/** "Oct 6" from an ISO date. */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

export function tone(v: number | null | undefined): 'up' | 'down' | 'flat' {
  if (v == null || !Number.isFinite(v) || v === 0) return 'flat';
  return v > 0 ? 'up' : 'down';
}
