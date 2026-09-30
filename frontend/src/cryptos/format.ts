/** How the Cryptos page writes its numbers. Unknown (null) is always an em dash, never 0. */

export const MINUS = '−';
export const DASH = '—';

export function pct(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  const s = Math.abs(x).toFixed(digits);
  if (Number(s) === 0) return `${s}%`;
  return `${x > 0 ? '+' : MINUS}${s}%`;
}

export function pt(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  const s = Math.abs(x).toFixed(digits);
  if (Number(s) === 0) return `${s} pt`;
  return `${x > 0 ? '+' : MINUS}${s} pt`;
}

export function usd(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  const a = Math.abs(x);
  const sign = x < 0 ? MINUS : '';
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e11) return `${sign}$${(a / 1e9).toFixed(0)}B`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(0)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

/** A headline figure: one more digit than the table's ("$148.2B", "$3.94T", "$412M"). */
export function usdFine(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  const a = Math.abs(x);
  const sign = x < 0 ? MINUS : '';
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  return usd(x);
}

/** A stock's price: dollars and cents. */
export function stockPrice(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return DASH;
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** A coin's headline price: whole dollars from $10,000, cents below. */
export function tilePrice(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return DASH;
  if (p >= 10_000) return `$${Math.round(p).toLocaleString('en-US')}`;
  if (p >= 1) return `$${p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `$${price(p)}`;
}

/** "PEPE, DOGE and SOL". */
export function listWords(items: string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** A flow: always signed ("+$412M", "−$88M"). */
export function usdSigned(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  const body = usd(Math.abs(x));
  return x > 0 ? `+${body}` : x < 0 ? `${MINUS}${body}` : body;
}

export function price(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return DASH;
  if (p >= 1000) return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p >= 100) return p.toFixed(2);
  if (p >= 1) return p.toFixed(3);
  if (p >= 0.01) return p.toFixed(4);
  return p.toFixed(8);
}

/** A whole-dollar level on a chart axis: "112,480". */
export function level(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return DASH;
  if (p >= 1000) return Math.round(p).toLocaleString('en-US');
  return price(p);
}

export function mult(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  return `${x.toFixed(digits)}×`;
}

export function funding(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  const s = Math.abs(x).toFixed(3);
  if (Number(s) === 0) return `${s}%`;
  return `${x > 0 ? '+' : MINUS}${s}%`;
}

export function tone(x: number | null | undefined): 'is-up' | 'is-down' | 'is-flat' {
  if (x === null || x === undefined || !Number.isFinite(x) || x === 0) return 'is-flat';
  return x > 0 ? 'is-up' : 'is-down';
}

const ET_TIME = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false });
const ET_DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short' });
const ET_DATE = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' });

/** "23:08" on the ET clock. */
export function timeEt(ts: number | null | undefined): string {
  if (ts === null || ts === undefined || !Number.isFinite(ts)) return DASH;
  return ET_TIME.format(new Date(ts * 1000)).replace(/^24:/, '00:');
}

/** "Wed 04:00" on the ET clock. */
export function dayTimeEt(ts: number | null | undefined): string {
  if (ts === null || ts === undefined || !Number.isFinite(ts)) return DASH;
  return `${ET_DAY.format(new Date(ts * 1000))} ${timeEt(ts)}`;
}

/** "Sep 29" on the ET clock. */
export function dateEt(ts: number | null | undefined): string {
  if (ts === null || ts === undefined || !Number.isFinite(ts)) return DASH;
  return ET_DATE.format(new Date(ts * 1000));
}

/** "4h 52m", "12m", "45s". */
export function countdown(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return DASH;
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

/** "12 s ago", "4 min ago", "2 h ago". */
export function ago(ts: number | null | undefined, now: number): string {
  if (ts === null || ts === undefined || !Number.isFinite(ts)) return 'never';
  const s = Math.max(0, Math.round(now - ts));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return `${Math.floor(s / 3600)} h ago`;
}

/** Minutes after ET midnight as "04:00". */
export function minutesEt(m: number): string {
  const h = Math.floor(m / 60) % 24;
  return `${String(h).padStart(2, '0')}:${String(Math.round(m % 60)).padStart(2, '0')}`;
}
