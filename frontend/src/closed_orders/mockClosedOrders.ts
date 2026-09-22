/**
 * UI-only sample closed orders for preview when Gateway has none.
 * Never treated as broker truth — same isolation pattern as mockWorkingOrders.
 *
 * Covers every terminal status in IBKR_CLOSED_ORDER_STATUSES:
 * Filled, Cancelled, ApiCancelled, Inactive — including cancel-after-partial.
 *
 * Time Placed (`submitted_at`) is always a fixed absolute ISO string -- the
 * recent-highlight row 9008's is frozen once at module load, 2.1 s before its
 * fill (QA W31). Never call Date.now() / toISOString() inside
 * buildMockClosedOrders — the sample list rebuilds on poll/render and would
 * make stamps crawl.
 */

import { samplePriceAt } from '../ibkr/mockWorkingOrders';
import type { ClosedOrder } from './types';

/**
 * Activity stamp for row 9008 — frozen once per JS module load so rebuilds
 * do not crawl milliseconds. Used only for the “recent completion” highlight.
 */
const MOCK_RECENT_ACTIVITY_AT = new Date().toISOString();
/**
 * 9008 is placed 2.1 s before that activity -- its own fill audit's
 * place-to-fill -- so the demo row never reads "placed Jul 18, filled just
 * now" (QA W31). Frozen at module load like the activity stamp.
 */
const MOCK_RECENT_PLACED_AT = new Date(Date.parse(MOCK_RECENT_ACTIVITY_AT) - 2_100).toISOString();

/** The price the closed sample set is written around. */
const MOCK_CLOSED_ANCHOR = 12.5;

/** Terminal IBKR statuses for Closed Orders (mirrors backend constants_ibkr). */
export const MOCK_CLOSED_IBKR_STATUSES = [
  'Filled',
  'Cancelled',
  'ApiCancelled',
  'Inactive',
] as const;

export const MOCK_CLOSED_TIMES = {
  // Filled → filled_at set (equals fill activity). Cancel/Inactive with zero
  // fills → filled_at null. Partial-then-cancel still filled_at set (real fill).
  9001: {
    submitted_at: '2026-07-18T12:00:00.000Z',
    updated_at: '2026-07-18T12:05:00.000Z',
    filled_at: '2026-07-18T12:05:00.000Z',
  },
  9002: {
    submitted_at: '2026-07-18T12:10:00.000Z',
    updated_at: '2026-07-18T12:11:00.000Z',
    filled_at: '2026-07-18T12:11:00.000Z',
  },
  9003: {
    submitted_at: '2026-07-18T12:20:00.000Z',
    updated_at: '2026-07-18T12:25:00.000Z',
    filled_at: null,
  },
  9004: {
    submitted_at: '2026-07-18T12:30:00.000Z',
    updated_at: '2026-07-18T12:40:00.000Z',
    filled_at: '2026-07-18T12:40:00.000Z',
  },
  9005: {
    submitted_at: '2026-07-18T12:45:00.000Z',
    updated_at: '2026-07-18T12:50:00.000Z',
    filled_at: '2026-07-18T12:50:00.000Z',
  },
  9006: {
    submitted_at: '2026-07-18T13:00:00.000Z',
    updated_at: '2026-07-18T13:01:00.000Z',
    filled_at: null,
  },
  9007: {
    submitted_at: '2026-07-18T13:10:00.000Z',
    updated_at: '2026-07-18T13:12:00.000Z',
    filled_at: null,
  },
  /** Time Placed for the recent-highlight demo row: 2.1 s before its fill, frozen at load. */
  9008: {
    submitted_at: MOCK_RECENT_PLACED_AT,
    updated_at: MOCK_RECENT_ACTIVITY_AT,
  },
} as const;

/**
 * The closed sample set for `symbol`; `anchor` (its own price) moves the
 * sample prices next to it, so a $4.25 stock's sample fills are not at $12.48.
 */
export function buildMockClosedOrders(symbol?: string | null, anchor?: number | null): ClosedOrder[] {
  const sym = (symbol?.trim() || 'DEMO').toUpperCase();
  const rows = writtenRows(sym);
  if (anchor == null) return rows;
  return rows.map((row) => (row.symbol !== sym ? row : {
    ...row,
    limit_price: samplePriceAt(row.limit_price, MOCK_CLOSED_ANCHOR, anchor),
    stop_price: samplePriceAt(row.stop_price ?? null, MOCK_CLOSED_ANCHOR, anchor),
    avg_fill_price: samplePriceAt(row.avg_fill_price ?? null, MOCK_CLOSED_ANCHOR, anchor),
  }));
}

function writtenRows(sym: string): ClosedOrder[] {
  return [
    {
      order_id: 9001,
      symbol: sym,
      side: 'BUY',
      qty: 100,
      filled_qty: 100,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 12.5,
      stop_price: null,
      avg_fill_price: 12.48,
      outside_rth: false,
      status: 'Filled',
      ...MOCK_CLOSED_TIMES[9001],
    },
    {
      order_id: 9002,
      symbol: sym,
      side: 'SELL',
      qty: 50,
      filled_qty: 50,
      remaining_qty: 0,
      order_type: 'MKT',
      limit_price: null,
      stop_price: null,
      avg_fill_price: 13.1,
      outside_rth: false,
      status: 'Filled',
      ...MOCK_CLOSED_TIMES[9002],
      fill_audit: {
        place_to_submit_ms: 12,
        place_to_fill_ms: 180,
        place_to_terminal_ms: null,
        level: 'ok',
        reason: 'filled',
      },
    },
    // Cancelled with zero fills.
    {
      order_id: 9003,
      symbol: 'MSFT',
      side: 'BUY',
      qty: 25,
      filled_qty: 0,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 400,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: true,
      status: 'Cancelled',
      ...MOCK_CLOSED_TIMES[9003],
    },
    // Critical: only part filled, then cancelled — inventory remains.
    {
      order_id: 9004,
      symbol: sym,
      side: 'BUY',
      qty: 100,
      filled_qty: 35,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 12.6,
      stop_price: null,
      avg_fill_price: 12.59,
      outside_rth: false,
      status: 'Cancelled',
      ...MOCK_CLOSED_TIMES[9004],
    },
    // ApiCancelled after a small partial (broker / API path).
    {
      order_id: 9005,
      symbol: sym,
      side: 'SELL',
      qty: 80,
      filled_qty: 10,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 13.4,
      stop_price: null,
      avg_fill_price: 13.38,
      outside_rth: false,
      status: 'ApiCancelled',
      ...MOCK_CLOSED_TIMES[9005],
    },
    // ApiCancelled with zero fills.
    {
      order_id: 9006,
      symbol: sym,
      side: 'BUY',
      qty: 20,
      filled_qty: 0,
      remaining_qty: 0,
      order_type: 'STP',
      limit_price: null,
      stop_price: 11.5,
      avg_fill_price: null,
      outside_rth: false,
      status: 'ApiCancelled',
      ...MOCK_CLOSED_TIMES[9006],
    },
    // Inactive → UI "Failed".
    {
      order_id: 9007,
      symbol: sym,
      side: 'SELL',
      qty: 30,
      filled_qty: 0,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 14.0,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: false,
      status: 'Inactive',
      ...MOCK_CLOSED_TIMES[9007],
    },
    // Demo “just completed” highlight — Time Placed fixed; activity frozen at load.
    {
      order_id: 9008,
      symbol: sym,
      side: 'BUY',
      qty: 40,
      filled_qty: 40,
      remaining_qty: 0,
      order_type: 'MKT',
      limit_price: null,
      stop_price: null,
      avg_fill_price: 12.75,
      outside_rth: false,
      status: 'Filled',
      submitted_at: MOCK_CLOSED_TIMES[9008].submitted_at,
      updated_at: MOCK_RECENT_ACTIVITY_AT,
      filled_at: MOCK_RECENT_ACTIVITY_AT,
      fill_audit: {
        place_to_submit_ms: 20,
        place_to_fill_ms: 2100,
        place_to_terminal_ms: null,
        level: 'warn',
        reason: 'mkt_rth_slow',
      },
    },
  ];
}
