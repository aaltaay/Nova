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

/** Text tone for Buy/Sell — used instead of a Side column on order tables. */
export function orderSideClass(side: string): 'ibkr-side--buy' | 'ibkr-side--sell' | '' {
  const s = side.trim().toUpperCase();
  if (s === 'BUY') return 'ibkr-side--buy';
  if (s === 'SELL') return 'ibkr-side--sell';
  return '';
}

/** Full-row highlight class for Buy/Sell (Open + Closed order tables). */
export function orderSideRowClass(
  side: string,
): 'ibkr-order-row--buy' | 'ibkr-order-row--sell' | '' {
  const s = side.trim().toUpperCase();
  if (s === 'BUY') return 'ibkr-order-row--buy';
  if (s === 'SELL') return 'ibkr-order-row--sell';
  return '';
}

/** Long (qty>0) / short (qty<0) tone for Positions — same green/red language. */
export function positionSideClass(
  qty: number | null | undefined,
): 'ibkr-side--buy' | 'ibkr-side--sell' | '' {
  if (qty == null || !Number.isFinite(qty) || qty === 0) return '';
  return qty > 0 ? 'ibkr-side--buy' : 'ibkr-side--sell';
}

export function positionSideRowClass(
  qty: number | null | undefined,
): 'ibkr-order-row--buy' | 'ibkr-order-row--sell' | '' {
  if (qty == null || !Number.isFinite(qty) || qty === 0) return '';
  return qty > 0 ? 'ibkr-order-row--buy' : 'ibkr-order-row--sell';
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
    // Critical edge case: cancel after partial fill leaves inventory + a closed row.
    return hasPartial ? 'Cancelled (partial fill)' : 'Cancelled';
  }
  if (s === 'inactive') return 'Failed';

  // Working partials beat "Pending" — PreSubmitted can still have fills.
  if (hasPartial) return 'Partially filled';

  if (
    s === 'pendingsubmit' ||
    s === 'apipending' ||
    s === 'presubmitted'
  ) {
    return 'Pending';
  }

  if (s === 'submitted') return 'Working';

  if (s.includes('reject') || s.includes('fail')) return 'Failed';
  if (s.includes('cancel')) {
    return hasPartial ? 'Cancelled (partial fill)' : 'Cancelled';
  }
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
    case 'Cancelled (partial fill)':
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

/** Exact Eastern time with seconds for open/closed order rows. */
export function formatOrderDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d);
  return `${formatted} ET`;
}

/** Prefer last activity (fill/cancel); fall back to submitted. */
export function orderActivityIso(order: {
  updated_at?: string | null;
  submitted_at?: string | null;
}): string | null {
  return order.updated_at || order.submitted_at || null;
}

export function orderTimeTitle(order: {
  updated_at?: string | null;
  submitted_at?: string | null;
}): string {
  const submitted = formatOrderDateTime(order.submitted_at);
  const updated = formatOrderDateTime(order.updated_at);
  if (submitted === '—' && updated === '—') return 'Time unavailable from broker';
  if (submitted !== '—' && updated !== '—' && submitted !== updated) {
    return `Submitted ${submitted} · Updated ${updated}`;
  }
  if (updated !== '—') return `Updated ${updated}`;
  return `Submitted ${submitted}`;
}
