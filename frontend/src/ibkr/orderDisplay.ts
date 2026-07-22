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

/**
 * Exact Eastern Time Placed label for order rows.
 * Shows milliseconds whenever the ISO carries a fractional second (audit).
 * Machine truth stays on `<time dateTime={iso}>` (UTC ISO unchanged).
 */
export function formatOrderDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const hasFraction = /[T ]\d{2}:\d{2}:\d{2}\.\d/.test(iso);
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    ...(hasFraction ? { fractionalSecondDigits: 3 as const } : {}),
    hour12: false,
  }).format(d);
  return `${formatted} ET`;
}

/**
 * Time Placed — broker/Nova place-time snapshot only.
 * Must NOT use updated_at (fills / status ticks would make the clock crawl).
 */
export function orderSubmittedIso(order: {
  submitted_at?: string | null;
  updated_at?: string | null;
}): string | null {
  return order.submitted_at || null;
}

/** Last fill / cancel activity (recency highlight + tooltip); not Time Placed. */
export function orderActivityIso(order: {
  updated_at?: string | null;
  submitted_at?: string | null;
}): string | null {
  return order.updated_at || order.submitted_at || null;
}

/** Time Filled — real broker fill clock; null when the order never filled. */
export function orderFilledIso(order: { filled_at?: string | null }): string | null {
  return order.filled_at || null;
}

export function orderFilledTimeTitle(order: { filled_at?: string | null }): string {
  const filled = formatOrderDateTime(order.filled_at);
  if (filled === '—') {
    return 'Time Filled — order never filled';
  }
  return `Time Filled ${filled} (broker fill clock)`;
}

export function orderSubmittedTimeTitle(order: {
  submitted_at?: string | null;
  updated_at?: string | null;
}): string {
  const submitted = formatOrderDateTime(order.submitted_at);
  if (submitted === '—') {
    return 'Time Placed unavailable (no broker log or Nova place stamp)';
  }
  const updated = formatOrderDateTime(order.updated_at);
  if (updated !== '—' && updated !== submitted) {
    return `Time Placed ${submitted} · Last activity ${updated}`;
  }
  return `Time Placed ${submitted} (fixed at place — does not update on fills)`;
}

/** @deprecated Prefer orderSubmittedTimeTitle — kept for older call sites. */
export function orderTimeTitle(order: {
  updated_at?: string | null;
  submitted_at?: string | null;
}): string {
  return orderSubmittedTimeTitle(order);
}
