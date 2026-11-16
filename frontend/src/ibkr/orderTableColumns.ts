/**
 * The columns of the IBKR order / position tables: ids, default order, header words.
 * The saved order lives in `orderTableColumnStore`.
 */
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import { OWNER_WHOSE_COL, OWNER_WHOSE_COL_TITLE } from '../constantGroups/owners';
import { LIQUIDATION_META, POSITION_SIDE_META, SIDE_COLUMN_META } from './orderSide';

export type OrderTableId = 'working' | 'closed' | 'positions';

export type WorkingOrderColumnId =
  | 'order_id'
  | 'symbol'
  | 'side'
  | 'qty'
  | 'filled'
  | 'remaining'
  | 'type'
  | 'limit'
  | 'stop'
  | 'avg_fill'
  | 'commission'
  | 'latency'
  | 'status'
  | 'sent_by'
  | 'time'
  | 'session';

export type ClosedOrderColumnId =
  | 'order_id'
  | 'symbol'
  | 'side'
  | 'qty'
  | 'filled'
  | 'type'
  | 'limit'
  | 'avg_fill'
  | 'commission'
  | 'latency'
  | 'status'
  | 'sent_by'
  | 'time'
  | 'filled_at';

export type PositionColumnId =
  | 'symbol'
  | 'whose'
  | 'side'
  | 'liq'
  | 'qty'
  | 'avg_cost'
  | 'commission'
  | 'mkt_price'
  | 'mkt_value'
  | 'unrealized';

/** Left→right default for Open / Working Orders (Actions stay pinned right). */
export const DEFAULT_WORKING_ORDER_COLUMNS: WorkingOrderColumnId[] = [
  'symbol',
  'side',
  'qty',
  'status',
  'sent_by',
  'type',
  'filled',
  'remaining',
  'avg_fill',
  'limit',
  'stop',
  'commission',
  'latency',
  'time',
  'session',
  'order_id',
];

/**
 * Mirror Working left→right as closely as Closed columns allow
 * (no remaining / stop / session on Closed). Symbol first; times last.
 */
export const DEFAULT_CLOSED_ORDER_COLUMNS: ClosedOrderColumnId[] = [
  'symbol',
  'side',
  'qty',
  'status',
  'sent_by',
  'type',
  'filled',
  'avg_fill',
  'limit',
  'commission',
  'latency',
  'time',
  'filled_at',
  'order_id',
];

export const DEFAULT_POSITION_COLUMNS: PositionColumnId[] = [
  'symbol',
  'whose',
  'side',
  'qty',
  'avg_cost',
  'commission',
  'mkt_price',
  'liq',
  'mkt_value',
  'unrealized',
];

export const WORKING_COMPACT_HIDDEN: ReadonlySet<string> = new Set([
  'remaining',
  'stop',
  'session',
]);

export type ColumnMeta = {
  id: string;
  label: string;
  className: string;
  title?: string;
};

/** "Sent by" (operator report 2026-10-01): who placed the order -- you, KILL, the loss limit or a bot. */
const SENT_BY_META: ColumnMeta = {
  id: 'sent_by',
  label: 'Sent by',
  className: 'ibkr-col--text ibkr-col--sent-by',
  title:
    "Who sent the order: You, KILL, the daily loss limit, Nova's bot, Auto-entry, Approve or a bot through the API. Hover a cell for more · Drag headers to reorder",
};

export const WORKING_COLUMN_META: Record<WorkingOrderColumnId, ColumnMeta> = {
  order_id: {
    id: 'order_id',
    label: 'Order ID',
    className: 'ibkr-col--text ibkr-col--order-id',
  },
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text ibkr-col--symbol',
    title: TICKER_OPEN_TRADER_TITLE,
  },
  qty: {
    id: 'qty',
    label: 'Quantity',
    className: 'ibkr-col--num',
    title: 'Quantity (fractional shares shown) — green = Buy, red = Sell',
  },
  filled: {
    id: 'filled',
    label: 'Filled',
    className: 'ibkr-col--num',
    title:
      'Shares filled so far (IBKR orderStatus.filled; fractional OK) — watch with Remaining while the order is working',
  },
  remaining: {
    id: 'remaining',
    label: 'Remaining',
    className: 'ibkr-col--num',
    title:
      'Shares still working — Fill now markets this remainder after cancelling the rest',
  },
  type: { id: 'type', label: 'Type', className: 'ibkr-col--type' },
  limit: { id: 'limit', label: 'Limit price', className: 'ibkr-col--num' },
  stop: { id: 'stop', label: 'Stop price', className: 'ibkr-col--num' },
  avg_fill: {
    id: 'avg_fill',
    label: 'Average fill',
    className: 'ibkr-col--num',
    title: 'Average fill price of shares filled so far (blank until first fill)',
  },
  commission: {
    id: 'commission',
    label: 'Commissions',
    className: 'ibkr-col--num ibkr-col--commission',
    title:
      'IBKR CommissionReport sum for this order -- blank until a real report; never invented from avg cost',
  },
  latency: {
    id: 'latency',
    label: 'Latency',
    className: 'ibkr-col--num ibkr-col--latency',
    title:
      'Click-to-fill when filled, else click-to-terminal. Hover for Nova→submit and submit→fill. MKT RTH warn/danger from fill-audit detective. Em dash when audit is missing -- never invented',
  },
  status: { id: 'status', label: 'Status', className: 'ibkr-col--status' },
  sent_by: SENT_BY_META,
  side: SIDE_COLUMN_META,
  time: {
    id: 'time',
    label: 'Time Placed',
    className: 'ibkr-col--time',
    title:
      'Time Placed — broker place time (Eastern, sub-seconds when provided); fixed at send, not last fill · Drag headers to reorder',
  },
  session: { id: 'session', label: 'Session', className: 'ibkr-col--type' },
};

export const CLOSED_COLUMN_META: Record<ClosedOrderColumnId, ColumnMeta> = {
  order_id: {
    id: 'order_id',
    label: 'Order ID',
    className: 'ibkr-col--text ibkr-col--order-id',
  },
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text ibkr-col--symbol',
    title: TICKER_OPEN_TRADER_TITLE,
  },
  qty: {
    id: 'qty',
    label: 'Quantity',
    className: 'ibkr-col--num',
    title: 'Quantity (fractional shares shown) — green = Buy, red = Sell',
  },
  filled: {
    id: 'filled',
    label: 'Filled',
    className: 'ibkr-col--num',
    title:
      'Shares filled before the order closed (fractional OK) — may be less than Quantity after a partial cancel',
  },
  type: { id: 'type', label: 'Type', className: 'ibkr-col--type' },
  limit: { id: 'limit', label: 'Limit price', className: 'ibkr-col--num' },
  avg_fill: {
    id: 'avg_fill',
    label: 'Average fill',
    className: 'ibkr-col--num',
    title: 'Average fill price of shares that filled (blank if none filled)',
  },
  commission: {
    id: 'commission',
    label: 'Commissions',
    className: 'ibkr-col--num ibkr-col--commission',
    title:
      'IBKR CommissionReport sum for this order -- blank until a real report; never invented from avg cost',
  },
  latency: {
    id: 'latency',
    label: 'Latency',
    className: 'ibkr-col--num ibkr-col--latency',
    title:
      'Click-to-fill when filled, else click-to-terminal. Hover for Nova→submit and submit→fill. MKT RTH warn/danger from fill-audit detective. Em dash when audit is missing -- never invented',
  },
  status: { id: 'status', label: 'Status', className: 'ibkr-col--status' },
  sent_by: SENT_BY_META,
  side: SIDE_COLUMN_META,
  time: {
    id: 'time',
    label: 'Time Placed',
    className: 'ibkr-col--time',
    title:
      'Time Placed — broker place time (Eastern, sub-seconds when provided); hover for last fill/cancel · Drag headers to reorder',
  },
  filled_at: {
    id: 'filled_at',
    label: 'Time Filled',
    className: 'ibkr-col--time',
    title:
      'Time Filled — broker fill time (Eastern, sub-seconds when provided); — when the order never filled · Drag headers to reorder',
  },
};

export const POSITION_COLUMN_META: Record<PositionColumnId, ColumnMeta> = {
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text ibkr-col--symbol',
    title: TICKER_OPEN_TRADER_TITLE,
  },
  // Paper and Sim: the table drops it on Live, where every row is yours (ADR 072).
  whose: {
    id: 'whose',
    label: OWNER_WHOSE_COL,
    className: 'ibkr-col--text ibkr-col--whose',
    title: OWNER_WHOSE_COL_TITLE,
  },
  qty: {
    id: 'qty',
    label: 'Qty',
    className: 'ibkr-col--num',
    title: 'Qty (fractional shares shown) — green = long, red = short',
  },
  avg_cost: { id: 'avg_cost', label: 'Avg Cost', className: 'ibkr-col--num' },
  commission: {
    id: 'commission',
    label: 'Commissions',
    className: 'ibkr-col--num ibkr-col--commission',
    title:
      'Session CommissionReport sum for this symbol -- blank until IBKR sends a report; not avg_cost minus fill',
  },
  side: POSITION_SIDE_META,
  liq: LIQUIDATION_META,
  mkt_price: { id: 'mkt_price', label: 'Mkt Price', className: 'ibkr-col--num' },
  mkt_value: { id: 'mkt_value', label: 'Mkt Value', className: 'ibkr-col--num' },
  unrealized: { id: 'unrealized', label: 'Unrealized P&L', className: 'ibkr-col--num' },
};

export function visibleWorkingColumns(
  order: string[],
  compact: boolean,
): WorkingOrderColumnId[] {
  return order.filter((id) => {
    if (compact && WORKING_COMPACT_HIDDEN.has(id)) return false;
    return id in WORKING_COLUMN_META;
  }) as WorkingOrderColumnId[];
}
