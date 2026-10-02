/**
 * Buying power after a practice fill, by the practice ledger's own rules
 * (QA W28, 2026-09-22). The ticket's "BP after" was buying power minus (or
 * plus) the order value; the ledger charges the fill's commission and fees,
 * re-marks the whole position at the fill price, and multiplies equity by 4x
 * (1x under the USD 2,000 margin minimum) -- so a 100-share buy at 1.49 read $399,424 where
 * the ledger lands at about $399,420. Mirrors backend practice/fees.py and
 * practice/margin.py; pure except that the fee date defaults to the wall clock.
 */
import {
  PRACTICE_CASH_MULT,
  PRACTICE_COMMISSION_MAX_PCT,
  PRACTICE_COMMISSION_MIN,
  PRACTICE_COMMISSION_PER_SHARE,
  PRACTICE_FINRA_CAT_PER_SHARE,
  PRACTICE_FINRA_TAF_HOLIDAYS,
  PRACTICE_FINRA_TAF_MAX,
  PRACTICE_FINRA_TAF_PER_SHARE,
  PRACTICE_MARGIN_INTRADAY_MULT,
  PRACTICE_MARGIN_MIN_EQUITY,
  PRACTICE_SEC_FEE_RATE,
} from '../constantGroups/practice';

const finite = (n: number | null | undefined): number | null =>
  typeof n !== 'number' || !Number.isFinite(n) ? null : n;

/** IBKR Fixed commission: per share, never below the minimum, never above the percent cap (the cap wins). */
export function practiceCommission(qty: number, price: number): number {
  const shares = Math.abs(qty);
  const px = Math.abs(price);
  if (!(shares > 0) || !(px > 0)) return 0;
  const cap = PRACTICE_COMMISSION_MAX_PCT * shares * px;
  return Math.min(Math.max(shares * PRACTICE_COMMISSION_PER_SHARE, PRACTICE_COMMISSION_MIN), cap);
}

const ET_DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
});

/** True when the Eastern trade date of `atMs` falls in a FINRA TAF holiday. */
export function practiceTafHoliday(atMs: number): boolean {
  if (!Number.isFinite(atMs)) return false;
  const day = ET_DAY.format(new Date(atMs));
  return PRACTICE_FINRA_TAF_HOLIDAYS.some(([start, end]) => start <= day && day <= end);
}

/**
 * Everything one fill traded at `atMs` is charged: commission and FINRA CAT,
 * plus SEC and FINRA TAF on a sell (no TAF on a TAF holiday). The ticket
 * estimates a fill now, so it passes the wall clock; a Sim replay of another
 * day may differ from the ledger by the TAF's pennies.
 */
export function practiceFees(side: 'BUY' | 'SELL', qty: number, price: number, atMs: number = Date.now()): number {
  const commission = practiceCommission(qty, price);
  if (!(commission > 0)) return 0;
  const shares = Math.abs(qty);
  const cat = shares * PRACTICE_FINRA_CAT_PER_SHARE;
  if (side !== 'SELL') return commission + cat;
  const sec = shares * Math.abs(price) * PRACTICE_SEC_FEE_RATE;
  const taf = practiceTafHoliday(atMs) ? 0 : Math.min(shares * PRACTICE_FINRA_TAF_PER_SHARE, PRACTICE_FINRA_TAF_MAX);
  return commission + cat + sec + taf;
}

export function practiceMultiplier(netLiquidation: number): number {
  return netLiquidation >= PRACTICE_MARGIN_MIN_EQUITY ? PRACTICE_MARGIN_INTRADAY_MULT : PRACTICE_CASH_MULT;
}

export interface PracticeFillInput {
  netLiquidation: number | null;
  grossPositionValue: number | null;
  side: 'BUY' | 'SELL';
  qty: number;
  /** The price the fill is estimated at. */
  price: number;
  /** Shares already held in the symbol (negative short; practice never shorts). */
  heldQty: number;
  /** The held position's current mark; the fill re-marks it at `price`. */
  heldMark: number | null;
  /** When the fill trades (epoch ms), for the TAF holiday; the wall clock when omitted. */
  atMs?: number;
}

/**
 * `max(0, equity' x multiplier(equity') - gross position value')` after the
 * fill, where the fill costs its fees out of equity and re-marks the held
 * shares at the fill price. Null when the account's figures are not known.
 */
export function practiceBuyingPowerAfter(input: PracticeFillInput): number | null {
  const nlv = finite(input.netLiquidation);
  const gpv = finite(input.grossPositionValue);
  if (nlv == null || gpv == null || !(input.qty > 0) || !(input.price > 0)) return null;
  const held = finite(input.heldQty) ?? 0;
  const mark = finite(input.heldMark) ?? input.price;
  const after = input.side === 'BUY' ? held + input.qty : held - input.qty;
  const equity = nlv + held * (input.price - mark) - practiceFees(input.side, input.qty, input.price, input.atMs);
  const gross = gpv - Math.abs(held * mark) + Math.abs(after * input.price);
  return Math.max(0, equity * practiceMultiplier(equity) - gross);
}
