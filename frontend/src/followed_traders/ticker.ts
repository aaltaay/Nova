/**
 * A followed trade's ticker when the feed may have read it glued to its price: with no space between them on the
 * stream's bar, OCR can take the ticker's last letter for a digit ("SOFI 14.03" read SOF 114.03). The backend checks
 * such a read against IBKR's tape at the entry (architecture/schema/followed-traders.md, "A ticker glued to its
 * price"); this says what the page shows for it. Pure.
 */
import type { BarPosition, FollowedTicker } from './types';

/** True while the trade's ticker may be wrong (checking, or neither reading fits IBKR's tape): nothing is priced. */
export function tickerUnsettled(t: { ticker?: FollowedTicker | null }): boolean {
  return t.ticker?.state === 'checking' || t.ticker?.state === 'unchecked';
}

// The digit OCR reads each of these letters as, the feed's own pairs.
const LETTER_TO_DIGIT: Record<string, string> = { I: '1', S: '5', B: '8', O: '0' };

/** A price as the bar writes it: two decimals, or the four it had. */
function barText(p: number): string {
  return Number(p.toFixed(2)) === p ? p.toFixed(2) : p.toFixed(4);
}

/** The ticker and price as OCR reads them glued together -- `SOFI 14.03` as `SOF 114.03` -- or null when the
 *  ticker's last letter is none OCR reads as a digit. */
export function gluedRead(symbol: string, price: number): Pick<BarPosition, 'symbol' | 'price'> | null {
  const digit = LETTER_TO_DIGIT[symbol.slice(-1)];
  if (!digit || symbol.length < 2) return null;
  return { symbol: symbol.slice(0, -1), price: Number(`${digit}${barText(price)}`) };
}
