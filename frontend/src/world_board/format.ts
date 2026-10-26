/** The world boards' number words (the Global and Forex pages, ADR 060, 062): dollars, signed percents, clocks.
 * Unknown is "--", never 0. */

const DASH = '--';
const MINUS = '−';

function sign(v: number): string {
  return v > 0 ? '+' : v < 0 ? MINUS : '';
}

function scaled(a: number): string {
  return a >= 1e12 ? `${(a / 1e12).toFixed(2)}T`
    : a >= 1e9 ? `${(a / 1e9).toFixed(a >= 1e11 ? 0 : 1)}B`
      : a >= 1e6 ? `${(a / 1e6).toFixed(a >= 1e8 ? 0 : 1)}M`
        : a >= 1e3 ? `${(a / 1e3).toFixed(1)}K`
          : a.toFixed(0);
}

/** The next unit's size, for a value that rounds up to 1,000 of its own. */
const NEXT_UNIT: Record<string, number> = { '': 1e3, K: 1e6, M: 1e9, B: 1e12 };

/** "$4.6B" / "$870M" / "$12.4K" -- or signed, "+$4.6B" / "−$870M". A value that rounds up to 1,000 of its unit reads
 * in the next one: "$1.0B", never "$1000M". */
export function usd(v: number | null | undefined, signed = false): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const a = Math.abs(v);
  let body = scaled(a);
  const rolled = /^1000(?:\.0+)?([KMB]?)$/.exec(body);
  if (rolled) body = scaled(NEXT_UNIT[rolled[1]]);
  return `${signed ? sign(v) : v < 0 ? MINUS : ''}$${body}`;
}

/** A market's size, as approximate as its source: "$68.0T", "$903B". */
export function sizeUsd(v: number | null | undefined): string {
  return v != null && Math.abs(v) >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : usd(v);
}

/** "Jan 2026" for a figure's month, "2026-01". */
export function monthWord(asOf: string): string {
  const [y, m] = asOf.split('-').map(Number);
  if (!y || !m) return asOf;
  return `${new Date(Date.UTC(y, m - 1, 1)).toLocaleString('en-US', { month: 'short', timeZone: 'UTC' })} ${y}`;
}

export function signedPct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${sign(v)}${Math.abs(v).toFixed(digits)}%`;
}

export function tone(v: number | null | undefined): 'up' | 'down' | 'flat' {
  if (v == null || !Number.isFinite(v) || v === 0) return 'flat';
  return v > 0 ? 'up' : 'down';
}

function clock(ts: number, timeZone: string): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone, hour: '2-digit', minute: '2-digit', hour12: false });
}

/** "09:41" on the ET clock. */
export function etTime(ts: number | null | undefined): string {
  return ts == null ? DASH : clock(ts, 'America/New_York');
}

/** "21:41" on the market's own clock. */
export function localTime(ts: number | null | undefined, timeZone: string): string {
  return ts == null ? DASH : clock(ts, timeZone);
}

/** "Tue Oct 20" on the ET clock. */
export function etDay(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-US', {
    timeZone: 'America/New_York', weekday: 'short', month: 'short', day: 'numeric',
  });
}

/** "Tue 21:41" on the ET clock, or "21:41" when it is the same ET day as `now`. */
export function etWhen(ts: number | null | undefined, now: number): string {
  if (ts == null) return DASH;
  const day = (t: number) => new Date(t * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
  if (day(ts) === day(now)) return etTime(ts);
  const weekday = new Date(ts * 1000).toLocaleDateString('en-US', { timeZone: 'America/New_York', weekday: 'short' });
  return `${weekday} ${etTime(ts)}`;
}

/** "in 2h 05m" / "in 7m" until `ts`. */
export function until(ts: number | null | undefined, now: number): string {
  if (ts == null) return DASH;
  const minutes = Math.max(0, Math.round((ts - now) / 60));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `in ${h}h ${String(m).padStart(2, '0')}m` : `in ${m}m`;
}

/** IBKR's reason up to its first sentence ("354: Requested market data is not subscribed."); the rest is its boilerplate. */
export function firstSentence(text: string): string {
  const end = text.indexOf('. ');
  return end > 0 ? text.slice(0, end + 1) : text;
}
