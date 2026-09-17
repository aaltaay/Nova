import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL, IBKR_ORDERS_POLL_MS } from '../constants';
import { lastKnownAsOfMessage } from '../ibkr/disconnectCopy';
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import type { ClosedOrder } from './types';

interface State {
  orders: ClosedOrder[];
  loading: boolean;
  /** Set when the last poll failed to read closed orders — `orders` above
   * is the last-good list, not an honest "no closed orders" read. */
  error: string | null;
  refresh: () => void;
}

function useClosedOrdersPoll(enabled: boolean): State {
  const [orders, setOrders] = useState<ClosedOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/ibkr/orders/closed`);
      if (res.ok) {
        setOrders((await res.json()) as ClosedOrder[]);
        setError(null);
      } else {
        setError(`closed orders unavailable (HTTP ${res.status})`);
      }
    } catch (err) {
      console.error('[Nova] closed orders fetch failed', err);
      setError('closed orders fetch failed — retrying');
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let active = true;
    const tick = () => {
      if (active) void refresh();
    };
    tick();
    const id = setInterval(tick, IBKR_ORDERS_POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [enabled, refresh]);

  return { orders, loading, error, refresh };
}

/** Session terminal orders -- prefer the shared account poller when mounted. */
export function useClosedOrders(connected: boolean): State {
  const ctx = useOptionalIbkrAccountContext();
  const fallback = useClosedOrdersPoll(connected && !ctx);

  if (ctx) {
    const error = connected
      ? ctx.error
      : lastKnownAsOfMessage(ctx.staleSince ?? Date.now());
    return {
      orders: ctx.closedOrders ?? [],
      loading: ctx.loading,
      error,
      refresh: ctx.refresh,
    };
  }

  if (!connected) {
    return {
      ...fallback,
      error: lastKnownAsOfMessage(Date.now()),
    };
  }
  return fallback;
}
