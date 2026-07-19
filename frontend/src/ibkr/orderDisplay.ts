/**
 * Webull-clean display labels for working / open orders (WID-026).
 * Wire data stays IBKR (LMT, PreSubmitted, …); the table never shows those raw.
 */

export type OrderStatusTone = 'working' | 'pending' | 'partial' | 'filled' | 'cancelled' | 'failed';

export function formatOrderSide(side: string): string {
  const s = side.trim().toUpperCase();
  if (s === 'BUY') return 'Buy';
  if (s === 'SELL') return 'Sell';
  return side || '—';
}

export function formatOrderType(orderType: string): string {
  const t = orderType.trim().toUpperCase().replace(/[\s_-]+/g, '');
  switch (t) {
    case 'LMT':
    case 'LIMIT':
      return 'Limit Order';
    case 'MKT':
    case 'MARKET':
      return 'Market Order';
    case 'STP':
    case 'STOP':
      return 'Stop Order';
    case 'STPLMT':
    case 'STOPLIMIT':
      return 'Stop Limit Order';
    case 'TRAIL':
    case 'TRAILINGSTOP':
      return 'Trailing Stop Order';
    default:
      return orderType.trim() || '—';
  }
}

export function formatOrderStatus(
  status: string,
  filledQty: number,
  qty: number,
): string {
  const s = status.trim().toLowerCase();
  const hasPartial =
    Number.isFinite(filledQty) &&
    Number.isFinite(qty) &&
    filledQty > 0 &&
    filledQty < qty;

  if (s === 'filled') return 'Filled';
  if (s === 'cancelled' || s === 'canceled' || s === 'apicancelled') {
    return 'Cancelled';
  }
  if (s === 'inactive') return 'Failed';

  if (
    s === 'pendingsubmit' ||
    s === 'apipending' ||
    s === 'presubmitted'
  ) {
    return 'Pending';
  }

  if (s === 'submitted') {
    return hasPartial ? 'Partially filled' : 'Working';
  }

  if (hasPartial) return 'Partially filled';
  if (s.includes('reject') || s.includes('fail')) return 'Failed';
  if (s.includes('cancel')) return 'Cancelled';
  if (s.includes('fill')) return 'Filled';
  if (s.includes('pend') || s.includes('presub')) return 'Pending';

  return status.trim() || '—';
}

export function orderStatusTone(label: string): OrderStatusTone {
  switch (label) {
    case 'Working':
      return 'working';
    case 'Pending':
      return 'pending';
    case 'Partially filled':
      return 'partial';
    case 'Filled':
      return 'filled';
    case 'Cancelled':
      return 'cancelled';
    case 'Failed':
      return 'failed';
    default:
      return 'pending';
  }
}

export function formatExtendedHours(outsideRth: boolean): string {
  return outsideRth ? 'Extended hours' : 'Regular hours';
}
