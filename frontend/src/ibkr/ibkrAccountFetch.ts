/** Shared IBKR account REST reads for IbkrAccountProvider. */
import {
  normalizeAccountSummary,
  normalizeOrderList,
  normalizePositionList,
} from './orderRowNormalize';
import type { IbkrAccountSummary, IbkrOrder, IbkrPosition } from './types';

/**
 * GET `url` and shape the body with `parse`. Every way the answer can be
 * wrong -- an HTTP error, a body that does not parse, a body of the wrong
 * shape -- is a named failure for the caller's banner, never a cast that a
 * table later trips over (QA C2 / C3).
 */
export async function fetchJson<T>(
  url: string,
  label: string,
  parse: (raw: unknown) => T | null = (raw) => raw as T,
): Promise<{
  data: T | null;
  failure: string | null;
}> {
  const res = await fetch(url);
  if (!res.ok) {
    return { data: null, failure: `${label} (HTTP ${res.status})` };
  }
  let raw: unknown;
  try {
    raw = await res.json();
  } catch (err) {
    console.warn(`[Nova] ${label}: unreadable response`, err);
    return { data: null, failure: `${label} (unreadable response)` };
  }
  const data = parse(raw);
  return data == null
    ? { data: null, failure: `${label} (unexpected shape)` }
    : { data, failure: null };
}

export async function fetchAccountCluster(base: string): Promise<{
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[] | null;
  failures: string[];
}> {
  const [sum, pos] = await Promise.all([
    fetchJson<IbkrAccountSummary>(`${base}/api/ibkr/account`, 'account', normalizeAccountSummary),
    fetchJson<IbkrPosition[]>(`${base}/api/ibkr/positions`, 'positions', normalizePositionList),
  ]);
  return {
    summary: sum.data,
    positions: pos.data,
    failures: [sum.failure, pos.failure].filter((f): f is string => f != null),
  };
}

export async function fetchOrdersCluster(base: string): Promise<{
  orders: IbkrOrder[] | null;
  closedOrders: IbkrOrder[] | null;
  failures: string[];
}> {
  const [ord, closed] = await Promise.all([
    fetchJson<IbkrOrder[]>(`${base}/api/ibkr/orders`, 'orders', normalizeOrderList),
    fetchJson<IbkrOrder[]>(`${base}/api/ibkr/orders/closed`, 'closed orders', normalizeOrderList),
  ]);
  return {
    orders: ord.data,
    closedOrders: closed.data,
    failures: [ord.failure, closed.failure].filter((f): f is string => f != null),
  };
}
