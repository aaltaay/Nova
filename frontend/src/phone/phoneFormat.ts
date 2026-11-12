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

/** A share count without decimals, grouped: 1500 is "1,500". */
export function shares(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return DASH;
  return Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
}
