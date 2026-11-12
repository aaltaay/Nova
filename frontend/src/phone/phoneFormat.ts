/**
 * How the phone writes a number in a column a few characters wide. Each one goes through the desk's
 * own formatter and only drops what a narrow column cannot hold: the dollar sign on a price, the
 * second decimal on a percent. A missing fact is a dash, never a zero. Pure.
 */
import { formatMoney } from '../utils/formatMoney';
import { fmtPrice, roundsToZero } from '../utils/quoteFormat';

export const DASH = '—';

/** A price as the desk prints it, without the dollar sign: "4.82", "0.678", "1,204.50". */
export function px(p: number | null | undefined): string {
  return fmtPrice(p).replace('$', '');
}

/** A fraction as a signed percent with one decimal: 0.382 is "+38.2%". Flat is "0.0%", with no sign. */
export function pct1(frac: number | null | undefined): string {
  if (frac == null || !Number.isFinite(frac)) return DASH;
  const pct = frac * 100;
  if (roundsToZero(pct, 1)) return '0.0%';
  const sign = pct > 0 ? '+' : '';
  if (Math.abs(pct) >= 1000) return `${sign}${Math.round(pct).toLocaleString('en-US')}%`;
  return `${sign}${pct.toFixed(1)}%`;
}

/** Profit and loss: "+$412.60", "-$5.00", "$0.00". */
export function signedMoney(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return DASH;
  const text = formatMoney(n, decimals);
  return n > 0 && !roundsToZero(n, decimals) ? `+${text}` : text;
}

export type Tone = 'good' | 'bad' | '';

/** Green above zero, red below, plain when flat or unknown. */
export function toneOf(n: number | null | undefined, decimals = 2): Tone {
  if (n == null || !Number.isFinite(n) || roundsToZero(n, decimals)) return '';
  return n > 0 ? 'good' : 'bad';
}

export function toneClass(n: number | null | undefined, decimals = 2): string {
  const tone = toneOf(n, decimals);
  return tone ? `ph-${tone}` : '';
}

/** How long ago, short: "now", "9m ago", "2 h ago", "3 d ago". */
export function agoShort(ms: number): string {
  if (!Number.isFinite(ms)) return DASH;
  const min = Math.floor(Math.max(0, ms) / 60_000);
  if (min < 1) return 'now';
  if (min < 60) return `${min}m ago`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

const UNITS: readonly [number, string][] = [[1e3, 'K'], [1e6, 'M'], [1e9, 'B']];

/**
 * A count in at most five characters: "876K", "5.0M", "26.3M", "195M", "1.23B" reads "1.2B". One decimal under
 * 100 of a unit, none from there; a value that rounds to 1000 of a unit moves up one ("1.0M", never "1000K").
 * The desk's own formatter keeps one decimal throughout, which a phone column has no room for.
 */
export function compact(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs < 999.5) return `${sign}${Math.round(abs)}`;
  let i = 0;
  while (i + 1 < UNITS.length && abs >= UNITS[i + 1][0] * 0.9995) i += 1;
  let n = abs / UNITS[i][0];
  if (n >= 999.5 && i + 1 < UNITS.length) {
    i += 1;
    n = abs / UNITS[i][0];
  }
  return `${sign}${n >= 99.95 ? n.toFixed(0) : n.toFixed(1)}${UNITS[i][1]}`;
}

/** A relative volume in a narrow column: "14.2x", "3.61x", "150x". */
export function rvolShort(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '';
  if (v < 0.01) return '<0.01x';
  if (v >= 100) return `${v.toFixed(0)}x`;
  return `${v >= 10 ? v.toFixed(1) : Number(v.toFixed(2))}x`;
}

/** A share count without decimals, grouped: 1500 is "1,500". */
export function shares(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return DASH;
  return Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
}
