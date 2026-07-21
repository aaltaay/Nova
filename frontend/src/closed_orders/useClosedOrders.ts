import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import type { ClosedOrder } from './types';

interface State {
  orders: ClosedOrder[];
  loading: boolean;
  /** Set when the last poll failed to read closed orders — `orders` above
   * is the last-good list, not an honest "no closed orders" read. */
  error: string | null;
  refresh: () => void;
}

/** Polls GET /api/ibkr/orders/closed when connected (session terminal orders). */
export function useClosedOrders(connected: boolean): State {
  const [orders, setOrders] = useState<ClosedOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!connected) return;
    setLoading(true);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/ibkr/orders/closed`);
      if (res.ok) {
        setOrders((await res.json()) as ClosedOrder[]);
        setError(null);
      } else {
        // Keep last-good orders — a failed read is not "no closed orders".
        setError(`closed orders unavailable (HTTP ${res.status})`);
      }
    } catch (err) {
      console.error('[Nova] closed orders fetch failed', err);
      setError('closed orders fetch failed — retrying');
    } finally {
      setLoading(false);
    }
  }, [connected]);

  useEffect(() => {
    if (!connected) {
      setOrders([]);
      setError(null);
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

  return { orders, loading, error, refresh };
}
