/**
 * Persisted column order for IBKR order / position tables.
 * Drag headers to reorder; layout survives refresh via localStorage.
 */

export type OrderTableId = 'working' | 'closed' | 'positions';

export type WorkingOrderColumnId =
  | 'order_id'
  | 'symbol'
  | 'qty'
  | 'filled'
  | 'remaining'
  | 'type'
  | 'limit'
  | 'stop'
  | 'avg_fill'
  | 'status'
  | 'time'
  | 'session';

export type ClosedOrderColumnId =
  | 'order_id'
  | 'symbol'
  | 'qty'
  | 'filled'
  | 'type'
  | 'limit'
  | 'avg_fill'
  | 'status'
  | 'time'
  | 'filled_at';

export type PositionColumnId =
  | 'symbol'
  | 'qty'
  | 'avg_cost'
  | 'mkt_price'
  | 'mkt_value'
  | 'unrealized';

/** Left→right default for Open / Working Orders (Actions stay pinned right). */
export const DEFAULT_WORKING_ORDER_COLUMNS: WorkingOrderColumnId[] = [
  'time',
  'session',
  'type',
  'symbol',
  'qty',
  'status',
  'filled',
  'remaining',
  'limit',
  'stop',
  'avg_fill',
  'order_id',
];

/**
 * Mirror Open Orders left→right as closely as Closed columns allow
 * (no session / remaining / stop on Closed).
 */
export const DEFAULT_CLOSED_ORDER_COLUMNS: ClosedOrderColumnId[] = [
  'filled_at',
  'time',
  'type',
  'symbol',
  'qty',
  'status',
  'filled',
  'limit',
  'avg_fill',
  'order_id',
];

export const DEFAULT_POSITION_COLUMNS: PositionColumnId[] = [
  'symbol',
  'qty',
  'avg_cost',
  'mkt_price',
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

export const WORKING_COLUMN_META: Record<WorkingOrderColumnId, ColumnMeta> = {
  order_id: { id: 'order_id', label: 'Order ID', className: 'ibkr-col--text' },
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text',
    title: 'Click: Quote Panel · Double-click: Trader',
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
  status: { id: 'status', label: 'Status', className: 'ibkr-col--status' },
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
  order_id: { id: 'order_id', label: 'Order ID', className: 'ibkr-col--text' },
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text',
    title: 'Click: Quote Panel · Double-click: Trader',
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
  status: { id: 'status', label: 'Status', className: 'ibkr-col--status' },
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
    className: 'ibkr-col--text',
    title: 'Click: Quote Panel · Double-click: Trader',
  },
  qty: {
    id: 'qty',
    label: 'Qty',
    className: 'ibkr-col--num',
    title: 'Qty (fractional shares shown) — green = long, red = short',
  },
  avg_cost: { id: 'avg_cost', label: 'Avg Cost', className: 'ibkr-col--num' },
  mkt_price: { id: 'mkt_price', label: 'Mkt Price', className: 'ibkr-col--num' },
  mkt_value: { id: 'mkt_value', label: 'Mkt Value', className: 'ibkr-col--num' },
  unrealized: { id: 'unrealized', label: 'Unrealized P&L', className: 'ibkr-col--num' },
};

/** Keep saved order, drop unknowns, append any new defaults at the end. */
export function normalizeColumnOrder(
  saved: string[] | null | undefined,
  defaults: readonly string[],
): string[] {
  const allowed = new Set(defaults);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of saved ?? []) {
    if (!allowed.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  for (const id of defaults) {
    if (seen.has(id)) continue;
    out.push(id);
  }
  return out;
}

export function moveColumnOrder(
  order: string[],
  activeId: string,
  overId: string,
): string[] {
  const from = order.indexOf(activeId);
  const to = order.indexOf(overId);
  if (from < 0 || to < 0 || from === to) return order;
  const next = [...order];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export type OrderTableColumnStore = {
  working: string[];
  closed: string[];
  positions: string[];
};

export function defaultColumnStore(): OrderTableColumnStore {
  return {
    working: [...DEFAULT_WORKING_ORDER_COLUMNS],
    closed: [...DEFAULT_CLOSED_ORDER_COLUMNS],
    positions: [...DEFAULT_POSITION_COLUMNS],
  };
}

export function parseColumnStore(raw: string | null): OrderTableColumnStore {
  const base = defaultColumnStore();
  if (!raw) return base;
  try {
    const parsed = JSON.parse(raw) as Partial<OrderTableColumnStore>;
    return {
      working: normalizeColumnOrder(parsed.working, DEFAULT_WORKING_ORDER_COLUMNS),
      closed: normalizeColumnOrder(parsed.closed, DEFAULT_CLOSED_ORDER_COLUMNS),
      positions: normalizeColumnOrder(parsed.positions, DEFAULT_POSITION_COLUMNS),
    };
  } catch {
    return base;
  }
}

export function loadColumnStore(
  storageKey: string,
  storage: Pick<Storage, 'getItem'> = localStorage,
): OrderTableColumnStore {
  try {
    return parseColumnStore(storage.getItem(storageKey));
  } catch {
    return defaultColumnStore();
  }
}

export function saveColumnStore(
  storageKey: string,
  store: OrderTableColumnStore,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(storageKey, JSON.stringify(store));
  } catch {
    /* quota / private mode */
  }
}

export function visibleWorkingColumns(
  order: string[],
  compact: boolean,
): WorkingOrderColumnId[] {
  return order.filter((id) => {
    if (compact && WORKING_COMPACT_HIDDEN.has(id)) return false;
    return id in WORKING_COLUMN_META;
  }) as WorkingOrderColumnId[];
}
