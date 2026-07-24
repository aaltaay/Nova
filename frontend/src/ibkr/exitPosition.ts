/**
 * Pure helpers for position exit sizing (Phase G3 Nova Actions).
 */

/** Matches backend IBKR_FRACTIONAL_ORDER_API_MSG / Error 10243. */
export const FRACTIONAL_ORDER_API_MSG =
  'IBKR API cannot place fractional-share orders (Error 10243). Close leftovers in TWS / IB Gateway desktop.';

export type ExitPositionResult =
  | { ok: true; side: 'BUY' | 'SELL'; qty: number }
  | { ok: false; error: string };

/** Positive whole-share lot — IBKR's API rejects fractional totalQuantity. */
export function isWholeShareQty(qty: number): boolean {
  return Number.isFinite(qty) && qty > 0 && Math.abs(qty - Math.round(qty)) < 1e-9;
}

/** Close full position (Share=Pos). */
export function buildExitFullPosition(positionQty: number | null | undefined): ExitPositionResult {
  if (positionQty == null || positionQty === 0) {
    return { ok: false, error: 'No open position to exit' };
  }
  const qty = Math.abs(positionQty);
  if (!isWholeShareQty(qty)) {
    return { ok: false, error: FRACTIONAL_ORDER_API_MSG };
  }
  const side: 'BUY' | 'SELL' = positionQty > 0 ? 'SELL' : 'BUY';
  return { ok: true, side, qty };
}

/** Close a percent of position (Share=Pos*pct/100). */
export function buildExitPositionPercent(
  positionQty: number | null | undefined,
  percent: number,
): ExitPositionResult {
  if (positionQty == null || positionQty === 0) {
    return { ok: false, error: 'No open position to exit' };
  }
  if (!Number.isFinite(percent) || percent <= 0 || percent > 100) {
    return { ok: false, error: 'Exit percent must be between 0 and 100' };
  }
  const qty = Math.floor((Math.abs(positionQty) * percent) / 100);
  if (qty <= 0) {
    return { ok: false, error: 'Exit size rounds to zero shares' };
  }
  const side: 'BUY' | 'SELL' = positionQty > 0 ? 'SELL' : 'BUY';
  return { ok: true, side, qty };
}
