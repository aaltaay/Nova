/**
 * Order and position rows in the shape every table assumes (QA C2 / C3,
 * 2026-09-22).
 *
 * The account poller cast `/api/ibkr/orders`, `/orders/closed` and
 * `/positions` straight to their row types. A `200 {}` answer reached
 * `orders.filter` / `positions.find`, and a row whose `status` / `side` /
 * `order_type` was null, or whose `submitted_at` was a number, reached an
 * unguarded `.trim()` -- each time the app-shell boundary replaced the whole
 * desk. Rows are normalised here, once, where they are fetched: text fields
 * are strings, time fields are ISO strings or null, numbers are finite or
 * null, and a list that is not a list is a named failure, not a crash.
 * Well-formed rows come back value-for-value unchanged; absent optional keys
 * stay absent.
 */
import type { IbkrAccountSummary, IbkrOrder, IbkrPosition } from './types';

type Loose = Record<string, unknown>;

function isObject(value: unknown): value is Loose {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

const text = (value: unknown): string =>
  typeof value === 'string' ? value : value == null ? '' : String(value);

/** A finite number, a numeric string's number, else null. */
export function finiteOrNull(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

const isoOrNull = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() ? value : null;

const ORDER_TEXT = ['symbol', 'side', 'order_type', 'status'] as const;
const ORDER_NUMBERS_REQUIRED = ['qty'] as const;
const ORDER_NUMBERS_OPTIONAL = [
  'order_id',
  'perm_id',
  'filled_qty',
  'remaining_qty',
  'limit_price',
  'stop_price',
  'avg_fill_price',
  'commission',
] as const;
const ORDER_TIMES = ['submitted_at', 'updated_at', 'filled_at', 'held_until'] as const;

/** One order row, or null when the row is not an object at all. */
export function normalizeOrderRow(raw: unknown): IbkrOrder | null {
  if (!isObject(raw)) return null;
  const out: Loose = { ...raw };
  for (const key of ORDER_TEXT) out[key] = text(raw[key]);
  for (const key of ORDER_NUMBERS_REQUIRED) out[key] = finiteOrNull(raw[key]) ?? 0;
  for (const key of ORDER_NUMBERS_OPTIONAL) {
    if (key in raw) out[key] = finiteOrNull(raw[key]);
  }
  if (out.order_id == null) out.order_id = 0;
  for (const key of ORDER_TIMES) {
    if (key in raw) out[key] = isoOrNull(raw[key]);
  }
  if ('outside_rth' in raw) out.outside_rth = raw.outside_rth === true;
  if ('fill_audit' in raw && !isObject(raw.fill_audit)) out.fill_audit = null;
  return out as unknown as IbkrOrder;
}

/** One position row, or null when it names no symbol. */
export function normalizePositionRow(raw: unknown): IbkrPosition | null {
  if (!isObject(raw) || typeof raw.symbol !== 'string' || !raw.symbol.trim()) return null;
  const out: Loose = { ...raw, qty: finiteOrNull(raw.qty) ?? 0 };
  for (const key of ['market_price', 'market_value', 'avg_cost', 'commission', 'unrealized_pnl', 'realized_pnl']) {
    if (key in raw) out[key] = finiteOrNull(raw[key]);
  }
  return out as unknown as IbkrPosition;
}

/** A list of rows, or null when the answer is not a list (the caller names the failure). */
export function normalizeOrderList(raw: unknown): IbkrOrder[] | null {
  if (!Array.isArray(raw)) return null;
  return raw.map(normalizeOrderRow).filter((row): row is IbkrOrder => row != null);
}

export function normalizePositionList(raw: unknown): IbkrPosition[] | null {
  if (!Array.isArray(raw)) return null;
  return raw.map(normalizePositionRow).filter((row): row is IbkrPosition => row != null);
}

/** The account summary, or null when the answer is not an object. */
export function normalizeAccountSummary(raw: unknown): IbkrAccountSummary | null {
  return isObject(raw) ? (raw as unknown as IbkrAccountSummary) : null;
}
