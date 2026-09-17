/**
 * Display-only fill honesty -- never paint Failed+Filled or 2109-as-reject.
 * Wire filled_qty still comes from the API; this belt zeros reject rows
 * that have no execDetails clock.
 */
import { IBKR_SOFT_ORDER_WARNING_CODES } from '../constants';
import { formatOrderStatus } from './orderDisplay';

export function isRejectLikeStatus(status: string): boolean {
  const s = (status || '').trim().toLowerCase();
  return s === 'inactive' || s.includes('reject') || s.includes('fail');
}

export function displayFilledQty(order: {
  status: string;
  filled_qty?: number | null;
  filled_at?: string | null;
}): number {
  const qty = Number(order.filled_qty ?? 0);
  if (!Number.isFinite(qty) || qty <= 0) return 0;
  if (isRejectLikeStatus(order.status) && !order.filled_at) return 0;
  if (isRejectLikeStatus(order.status)) return 0;
  return qty;
}

export function isFailedPlusFilledLie(
  status: string,
  filledQty: number,
  qty = filledQty,
): boolean {
  const label = formatOrderStatus(status, filledQty, qty);
  return label === 'Failed' && filledQty > 0;
}

export function isSoftOrderWarning(
  message: string,
  reasonCode?: string | null,
): boolean {
  const text = (message || '').trim();
  if (!text) return false;
  if (/Warning\s*2109/i.test(text) || /outsideRth ignored/i.test(text)) {
    return true;
  }
  const match = text.match(/\b(?:Warning|Error)\s*(\d{3,5})\b/i);
  if (match) {
    const code = Number(match[1]);
    if (
      IBKR_SOFT_ORDER_WARNING_CODES.includes(
        code as (typeof IBKR_SOFT_ORDER_WARNING_CODES)[number],
      )
    ) {
      return true;
    }
  }
  return reasonCode === 'IBKR_SOFT_WARNING';
}

export function assertNoFailedPlusFilled(
  status: string,
  filledQty: number,
): void {
  if (isFailedPlusFilledLie(status, filledQty)) {
    throw new Error(`Failed+Filled lie: status=${status} filled=${filledQty}`);
  }
}
