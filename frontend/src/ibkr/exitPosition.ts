/**
 * Pure helpers for position exit sizing (Phase G3 Nova Actions).
 */

export type ExitPositionResult =
  | { ok: true; side: 'BUY' | 'SELL'; qty: number }
  | { ok: false; error: string };

/** Close full position (Share=Pos). */
export function buildExitFullPosition(positionQty: number | null | undefined): ExitPositionResult {
  if (positionQty == null || positionQty === 0) {
    return { ok: false, error: 'No open position to exit' };
  }
  const qty = Math.abs(positionQty);
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
