/**
 * Webull-clean display labels for working / open orders (WID-026).
 * Wire data stays IBKR (LMT, PreSubmitted, …); the table never shows those raw.
 *
 * Every helper takes whatever the wire sent (QA C2): a null status or a
 * numeric timestamp renders as "—" instead of throwing inside `.trim()`.
 */
import {
  ORDER_PRICE_PLAUSIBLE_MAX,
  ORDER_SESSION_PRACTICE,
  ORDER_SESSION_PRACTICE_TITLE,
} from '../constantGroups/order_display';

const asText = (value: unknown): string => (typeof value === 'string' ? value : '');

export type OrderStatusTone =
  | 'working'
  | 'pending'
  | 'partial'
  | 'filled'
  | 'cancelled'
  | 'failed'
  | 'unknown';

export function formatOrderSide(side: unknown): string {
  const raw = asText(side);
  const s = raw.trim().toUpperCase();
  if (s === 'BUY') return 'Buy';
  if (s === 'SELL') return 'Sell';
  return raw || '—';
}

/** Text tone for Buy/Sell — used instead of a Side column on order tables. */
export function orderSideClass(side: unknown): 'ibkr-side--buy' | 'ibkr-side--sell' | '' {
  const s = asText(side).trim().toUpperCase();
  if (s === 'BUY') return 'ibkr-side--buy';
  if (s === 'SELL') return 'ibkr-side--sell';
  return '';
}

/** Full-row highlight class for Buy/Sell (Open + Closed order tables). */
export function orderSideRowClass(
  side: unknown,
): 'ibkr-order-row--buy' | 'ibkr-order-row--sell' | '' {
  const s = asText(side).trim().toUpperCase();
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

export function formatOrderType(orderType: unknown): string {
  const raw = asText(orderType);
  const t = raw.trim().toUpperCase().replace(/[\s_-]+/g, '');
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
      return raw.trim() || '—';
  }
}

export function formatOrderStatus(
  status: unknown,
  filledQty: number,
  qty: number,
): string {
  const rawStatus = asText(status);
  const s = rawStatus.trim().toLowerCase();
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

  return rawStatus.trim() || '—';
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
      // A broker status Nova has no mapping for must not borrow the `pending`
      // tone — that reads as "still working" for an order nobody can vouch for.
      return 'unknown';
  }
}

export function formatExtendedHours(outsideRth: boolean): string {
  return outsideRth ? 'Extended hours' : 'Regular hours';
}

/**
 * A practice order (Paper / Sim, ADR 020): the practice broker stamps its
 * rows with `venue` and marks every one `fill_estimated`; IBKR rows carry
 * neither.
 */
export function isPracticeOrder(order: { venue?: unknown; fill_estimated?: unknown }): boolean {
  return order.venue === 'paper' || order.venue === 'sim' || order.fill_estimated === true;
}

/** Session cell: a practice order works in every session, so it says so (C30). */
export function formatOrderSession(order: {
  outside_rth?: unknown;
  venue?: unknown;
  fill_estimated?: unknown;
}): { label: string; title: string | undefined } {
  if (isPracticeOrder(order)) return { label: ORDER_SESSION_PRACTICE, title: ORDER_SESSION_PRACTICE_TITLE };
  return { label: formatExtendedHours(order.outside_rth === true), title: undefined };
}

/**
 * A price worth printing: finite, positive and below ORDER_PRICE_PLAUSIBLE_MAX.
 * IB's unset price (1.797e308) and any other placeholder read as null (C28).
 */
export function plausiblePrice(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 && value < ORDER_PRICE_PLAUSIBLE_MAX
    ? value
    : null;
}

/**
 * Exact Eastern Time Placed label for order rows.
 * Shows milliseconds whenever the ISO carries a fractional second (audit).
 * Machine truth stays on `<time dateTime={iso}>` (UTC ISO unchanged).
 */
function parseOrderInstant(iso: string): Date {
  const text = iso.trim();
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text);
  return new Date(hasZone ? text : `${text}Z`);
}

export function formatOrderDateTime(iso: unknown): string {
  if (typeof iso !== 'string' || !iso.trim()) return '—';
  const d = parseOrderInstant(iso);
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
