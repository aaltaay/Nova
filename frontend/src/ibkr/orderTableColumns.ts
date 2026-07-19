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
  | 'time';

export type PositionColumnId =
  | 'symbol'
  | 'qty'
  | 'avg_cost'
  | 'mkt_price'
  | 'mkt_value'
  | 'unrealized';

export const DEFAULT_WORKING_ORDER_COLUMNS: WorkingOrderColumnId[] = [
  'order_id',
  'symbol',
  'qty',
  'filled',
  'remaining',
  'type',
  'limit',
  'stop',
  'avg_fill',
  'status',
  'time',
  'session',
];

export const DEFAULT_CLOSED_ORDER_COLUMNS: ClosedOrderColumnId[] = [
  'order_id',
  'symbol',
  'qty',
  'filled',
  'type',
  'limit',
  'avg_fill',
  'status',
  'time',
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
    title: 'Click: Quote Panel · Double-click: Stock View',
  },
  qty: {
    id: 'qty',
    label: 'Quantity',
    className: 'ibkr-col--num',
    title: 'Quantity — green = Buy, red = Sell',
  },
  filled: { id: 'filled', label: 'Filled', className: 'ibkr-col--num' },
  remaining: { id: 'remaining', label: 'Remaining', className: 'ibkr-col--num' },
  type: { id: 'type', label: 'Type', className: 'ibkr-col--type' },
  limit: { id: 'limit', label: 'Limit price', className: 'ibkr-col--num' },
  stop: { id: 'stop', label: 'Stop price', className: 'ibkr-col--num' },
  avg_fill: { id: 'avg_fill', label: 'Average fill', className: 'ibkr-col--num' },
  status: { id: 'status', label: 'Status', className: 'ibkr-col--status' },
  time: {
    id: 'time',
    label: 'Time',
    className: 'ibkr-col--time',
    title: 'Last fill or status change (Eastern, seconds) · Drag headers to reorder',
  },
  session: { id: 'session', label: 'Session', className: 'ibkr-col--type' },
};

export const CLOSED_COLUMN_META: Record<ClosedOrderColumnId, ColumnMeta> = {
  order_id: { id: 'order_id', label: 'Order ID', className: 'ibkr-col--text' },
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text',
    title: 'Click: Quote Panel · Double-click: Stock View',
  },
  qty: {
    id: 'qty',
    label: 'Quantity',
    className: 'ibkr-col--num',
    title: 'Quantity — green = Buy, red = Sell',
  },
  filled: { id: 'filled', label: 'Filled', className: 'ibkr-col--num' },
  type: { id: 'type', label: 'Type', className: 'ibkr-col--type' },
  limit: { id: 'limit', label: 'Limit price', className: 'ibkr-col--num' },
  avg_fill: { id: 'avg_fill', label: 'Average fill', className: 'ibkr-col--num' },
  status: { id: 'status', label: 'Status', className: 'ibkr-col--status' },
  time: {
    id: 'time',
    label: 'Time',
    className: 'ibkr-col--time',
    title: 'Fill or cancel time (Eastern, seconds) · Drag headers to reorder',
  },
};

export const POSITION_COLUMN_META: Record<PositionColumnId, ColumnMeta> = {
  symbol: {
    id: 'symbol',
    label: 'Symbol',
    className: 'ibkr-col--text',
    title: 'Click: Quote Panel · Double-click: Stock View',
  },
  qty: {
    id: 'qty',
    label: 'Qty',
    className: 'ibkr-col--num',
    title: 'Qty — green = long, red = short',
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
