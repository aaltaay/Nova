/** Shared IBKR account REST reads for IbkrAccountProvider. */
import type { IbkrAccountSummary, IbkrOrder, IbkrPosition } from './types';

export async function fetchJson<T>(url: string, label: string): Promise<{
  data: T | null;
  failure: string | null;
}> {
  const res = await fetch(url);
  if (!res.ok) {
    return { data: null, failure: `${label} (HTTP ${res.status})` };
  }
  return { data: (await res.json()) as T, failure: null };
}

export async function fetchAccountCluster(base: string): Promise<{
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[] | null;
  failures: string[];
}> {
  const [sum, pos] = await Promise.all([
    fetchJson<IbkrAccountSummary>(`${base}/api/ibkr/account`, 'account'),
    fetchJson<IbkrPosition[]>(`${base}/api/ibkr/positions`, 'positions'),
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
    fetchJson<IbkrOrder[]>(`${base}/api/ibkr/orders`, 'orders'),
    fetchJson<IbkrOrder[]>(`${base}/api/ibkr/orders/closed`, 'closed orders'),
  ]);
  return {
    orders: ord.data,
    closedOrders: closed.data,
    failures: [ord.failure, closed.failure].filter((f): f is string => f != null),
  };
}
