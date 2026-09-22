/**
 * Which order a row is (QA C29, 2026-09-22).
 *
 * `order_id` alone is not an identity: ib_async replays completed orders with
 * orderId 0, and practice ids restart at 1 per venue and per reset. Tables
 * keyed and de-duplicated on it collided -- React warned about duplicate keys
 * and the Account page kept 1 of 4 filled rows. The identity is IB's durable
 * permId when there is one, else the execution-ledger row, else the order id
 * with its place time and symbol; practice rows carry their venue too.
 */
import type { IbkrOrder } from './types';

type Identifiable = Pick<IbkrOrder, 'order_id' | 'symbol' | 'side'> &
  Partial<Pick<IbkrOrder, 'perm_id' | 'execution_id' | 'submitted_at' | 'venue'>>;

const positiveInt = (value: unknown): number | null =>
  typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null;

export function orderIdentityKey(order: Identifiable): string {
  const venue = order.venue ?? '';
  const perm = positiveInt(order.perm_id);
  if (perm != null) return `perm:${venue}:${perm}`;
  if (typeof order.execution_id === 'string' && order.execution_id) return `exec:${order.execution_id}`;
  return `oid:${venue}:${order.order_id}:${order.submitted_at ?? ''}:${order.symbol}:${order.side}`;
}

/**
 * React keys for a list of rows: the identity, with a counter only on a
 * genuine repeat, so every sibling key is unique.
 */
export function orderRowKeys(orders: readonly Identifiable[]): string[] {
  const seen = new Map<string, number>();
  return orders.map((order) => {
    const key = orderIdentityKey(order);
    const n = seen.get(key) ?? 0;
    seen.set(key, n + 1);
    return n === 0 ? key : `${key}#${n}`;
  });
}

/** Rows with one entry per order, first occurrence kept (Account page Orders tab). */
export function uniqueOrders<T extends Identifiable>(orders: readonly T[]): T[] {
  const seen = new Set<string>();
  return orders.filter((order) => {
    const key = orderIdentityKey(order);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
