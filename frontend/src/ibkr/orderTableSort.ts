/**
 * Rich row-sort for Working / Closed order tables.
 * Click header → cycle; Shift+click → multi-sort stack; semantic ranks for
 * status / type / session (not raw IBKR wire strings).
 */
import { ORDER_TABLE_DATA_SORT_KEYS } from '../constants';
import { formatOrderStatus, orderFilledIso, orderSubmittedIso } from './orderDisplay';
import type { IbkrOrder } from './types';

export type OrderSortDir = 'asc' | 'desc';
export type OrderSortKey = (typeof ORDER_TABLE_DATA_SORT_KEYS)[number];
export type OrderSortLevel = { key: OrderSortKey; dir: OrderSortDir };
export type OrderSortState = OrderSortLevel[];
export type OrderSortMode = 'working' | 'closed';

const SORT_KEY_SET = new Set<string>(ORDER_TABLE_DATA_SORT_KEYS);

export function isOrderSortKey(id: string): id is OrderSortKey {
  return SORT_KEY_SET.has(id);
}

/** Working → Pending → Partial → Filled → cancel variants → Failed. */
const STATUS_RANK: Record<string, number> = {
  Working: 10,
  Pending: 20,
  'Partially filled': 30,
  Filled: 40,
  'Cancelled (partial fill)': 50,
  Cancelled: 60,
  Failed: 70,
};

/** Market → Limit → Stop → other. */
const TYPE_RANK: Record<string, number> = {
  MKT: 10,
  MARKET: 10,
  LMT: 20,
  LIMIT: 20,
  STP: 30,
  STOP: 30,
  STPLMT: 40,
  STOPLIMIT: 40,
};

function statusRank(o: IbkrOrder): number {
  const label = formatOrderStatus(o.status, o.filled_qty ?? 0, o.qty);
  return STATUS_RANK[label] ?? 100;
}

function typeRank(o: IbkrOrder): number {
  const t = (o.order_type || '').trim().toUpperCase().replace(/[\s_-]+/g, '');
  return TYPE_RANK[t] ?? 90;
}

function sessionRank(o: IbkrOrder): number {
  // Regular hours first on asc; Extended last.
  return o.outside_rth ? 1 : 0;
}

function timeMs(o: IbkrOrder, _mode: OrderSortMode): number {
  // Time Placed sorts by submitted_at for Working and Closed alike.
  const iso = orderSubmittedIso(o);
  if (!iso) return Number.NaN;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : Number.NaN;
}

function filledAtMs(o: IbkrOrder): number {
  const iso = orderFilledIso(o);
  if (!iso) return Number.NaN;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : Number.NaN;
}

function num(v: number | null | undefined): number {
  return v != null && Number.isFinite(v) ? v : Number.NaN;
}

/** Compare one field; NaN / missing sort last. */
export function compareOrderField(
  a: IbkrOrder,
  b: IbkrOrder,
  key: OrderSortKey,
  mode: OrderSortMode,
): number {
  let av: number | string = 0;
  let bv: number | string = 0;
  switch (key) {
    case 'type':
      av = typeRank(a);
      bv = typeRank(b);
      break;
    case 'session':
      av = sessionRank(a);
      bv = sessionRank(b);
      break;
    case 'time':
      av = timeMs(a, mode);
      bv = timeMs(b, mode);
      break;
    case 'filled_at':
      av = filledAtMs(a);
      bv = filledAtMs(b);
      break;
    case 'qty':
      av = num(a.qty);
      bv = num(b.qty);
      break;
    case 'status':
      av = statusRank(a);
      bv = statusRank(b);
      break;
    case 'filled':
      av = num(a.filled_qty);
      bv = num(b.filled_qty);
      break;
    case 'remaining':
      av = num(a.remaining_qty);
      bv = num(b.remaining_qty);
      break;
    case 'limit':
      av = num(a.limit_price);
      bv = num(b.limit_price);
      break;
    case 'stop':
      av = num(a.stop_price);
      bv = num(b.stop_price);
      break;
    case 'avg_fill':
      av = num(a.avg_fill_price);
      bv = num(b.avg_fill_price);
      break;
    case 'order_id':
      av = a.order_id;
      bv = b.order_id;
      break;
    case 'symbol':
      av = a.symbol.toUpperCase();
      bv = b.symbol.toUpperCase();
      break;
    default:
      return 0;
  }

  const aMissing =
    typeof av === 'number' ? !Number.isFinite(av) : av === '';
  const bMissing =
    typeof bv === 'number' ? !Number.isFinite(bv) : bv === '';
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  if (typeof av === 'number' && typeof bv === 'number') return av - bv;
  return String(av).localeCompare(String(bv));
}

/**
 * Click: set/cycle primary sort (asc → desc → off).
 * Shift+click: add/cycle/remove a level in the multi-sort stack.
 * Time defaults to desc on first activate (newest first).
 */
export function cycleOrderSort(
  state: OrderSortState,
  key: OrderSortKey,
  additive: boolean,
): OrderSortState {
  const firstDir: OrderSortDir = key === 'time' || key === 'filled_at' ? 'desc' : 'asc';

  if (additive) {
    const idx = state.findIndex((s) => s.key === key);
    if (idx === -1) return [...state, { key, dir: firstDir }];
    const cur = state[idx];
    if (cur.dir === firstDir) {
      const flipped: OrderSortDir = firstDir === 'asc' ? 'desc' : 'asc';
      const next = [...state];
      next[idx] = { key, dir: flipped };
      return next;
    }
    return state.filter((_, i) => i !== idx);
  }

  if (state.length === 1 && state[0].key === key) {
    if (state[0].dir === firstDir) {
      const flipped: OrderSortDir = firstDir === 'asc' ? 'desc' : 'asc';
      return [{ key, dir: flipped }];
    }
    return [];
  }
  return [{ key, dir: firstDir }];
}

export function sortOrders(
  orders: IbkrOrder[],
  state: OrderSortState,
  mode: OrderSortMode,
): IbkrOrder[] {
  if (!state.length) return orders;
  return [...orders].sort((a, b) => {
    for (const level of state) {
      const cmp = compareOrderField(a, b, level.key, mode);
      if (cmp !== 0) return level.dir === 'asc' ? cmp : -cmp;
    }
    return a.order_id - b.order_id;
  });
}

export function sortLevelFor(
  state: OrderSortState,
  key: string,
): { level: OrderSortLevel; index: number } | null {
  const index = state.findIndex((s) => s.key === key);
  if (index < 0) return null;
  return { level: state[index], index };
}
