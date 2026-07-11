import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { IbkrAccountSummary, IbkrPosition, IbkrOrder } from './types';

interface AccountState {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  loading: boolean;
  refresh: () => void;
}

/** Polls account summary, positions and open orders every 5 s when connected. */
export function useIbkrAccount(connected: boolean): AccountState {
  const [summary, setSummary] = useState<IbkrAccountSummary | null>(null);
  const [positions, setPositions] = useState<IbkrPosition[]>([]);
  const [orders, setOrders] = useState<IbkrOrder[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!connected) return;
    setLoading(true);
    try {
      const [sumRes, posRes, ordRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/ibkr/account`),
        fetch(`${API_BASE_URL}/api/ibkr/positions`),
        fetch(`${API_BASE_URL}/api/ibkr/orders`),
      ]);
      setSummary(sumRes.ok ? await sumRes.json() : null);
      setPositions(posRes.ok ? await posRes.json() : []);
      setOrders(ordRes.ok ? await ordRes.json() : []);
    } catch {
      // next poll will retry
    } finally {
      setLoading(false);
    }
  }, [connected]);

  useEffect(() => {
    if (!connected) {
      setSummary(null);
      setPositions([]);
      setOrders([]);
      setLoading(false);
      return;
    }

    let active = true;
    const tick = () => {
      if (active) refresh();
    };
    tick();
    const id = setInterval(tick, 5_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [connected, refresh]);

  return { summary, positions, orders, loading, refresh };
}
