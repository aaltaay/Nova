import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import type { ClosedOrder } from './types';

interface State {
  orders: ClosedOrder[];
  loading: boolean;
  refresh: () => void;
}

/** Polls GET /api/ibkr/orders/closed when connected (session terminal orders). */
export function useClosedOrders(connected: boolean): State {
  const [orders, setOrders] = useState<ClosedOrder[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!connected) return;
    setLoading(true);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/ibkr/orders/closed`);
      setOrders(res.ok ? ((await res.json()) as ClosedOrder[]) : []);
    } catch {
      /* next poll retries */
    } finally {
      setLoading(false);
    }
  }, [connected]);

  useEffect(() => {
    if (!connected) {
      setOrders([]);
      setLoading(false);
      return;
    }
    let active = true;
    const tick = () => {
      if (active) void refresh();
    };
    tick();
    const id = setInterval(tick, 5_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [connected, refresh]);

  return { orders, loading, refresh };
}
