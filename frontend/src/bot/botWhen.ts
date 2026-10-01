/**
 * When something happened or lifts, in Eastern time (ADR 042 D: one day boundary,
 * 04:00 ET). The backend sends epoch seconds or an ISO datetime; a legacy day lock
 * is a bare `YYYY-MM-DD`, which keeps its old meaning (it lifted at that date's
 * 00:00 ET). Unknown reads as empty -- the caller says what it does not know. Pure.
 */
const TZ = 'America/New_York';
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** Epoch milliseconds of an epoch-second number or an ISO string; null when unreadable. */
export function whenMs(value: string | number | null | undefined): number | null {
  if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value * 1000 : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  if (DATE_ONLY.test(value.trim())) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

/** "09:42 ET"; empty when unknown. */
export function etTime(value: string | number | null | undefined): string {
  const ms = whenMs(value);
  if (ms == null) return '';
  const t = new Date(ms).toLocaleTimeString('en-US', { timeZone: TZ, hour12: false, hour: '2-digit', minute: '2-digit' });
  return `${t} ET`;
}

function etDay(ms: number): string {
  return new Date(ms).toLocaleDateString('en-US', { timeZone: TZ, month: 'short', day: 'numeric' });
}

/** "04:00 ET on Oct 1" for when a lock or a latch lifts; a legacy date reads "00:00 ET on Sep 30". */
export function etUntil(value: string | number | null | undefined): string {
  if (typeof value === 'string' && DATE_ONLY.test(value.trim())) {
    const [y, m, d] = value.trim().split('-').map(Number);
    const day = new Date(Date.UTC(y, m - 1, d, 12)).toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });
    return `00:00 ET on ${day}`;
  }
  const ms = whenMs(value);
  if (ms == null) return '';
  return `${etTime(value)} on ${etDay(ms)}`;
}

/** Dollars and cents with a real minus sign: -52.1 -> "−$52.10"; empty when unknown. */
export function usdCents(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '';
  const text = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${v < 0 ? '−' : ''}$${text}`;
}
