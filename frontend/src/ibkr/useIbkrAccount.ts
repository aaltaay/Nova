import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { IbkrAccountSummary, IbkrPosition, IbkrOrder } from './types';

interface AccountState {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  loading: boolean;
  /** Set when the last poll failed — rows above may be last-good, not flat. */
  error: string | null;
  refresh: () => void;
}

/** Polls account summary, positions and open orders every 5 s when connected. */
export function useIbkrAccount(connected: boolean): AccountState {
  const [summary, setSummary] = useState<IbkrAccountSummary | null>(null);
  const [positions, setPositions] = useState<IbkrPosition[]>([]);
  const [orders, setOrders] = useState<IbkrOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!connected) return;
    setLoading(true);
    try {
      const [sumRes, posRes, ordRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/ibkr/account`),
        fetch(`${API_BASE_URL}/api/ibkr/positions`),
        fetch(`${API_BASE_URL}/api/ibkr/orders`),
      ]);
      // Non-OK reads are transport failures — keep last-good rows and surface
      // error so Flatten/exit can disable (last-good qty ≠ verified live gate).
      const failures: string[] = [];
      if (sumRes.ok) {
        setSummary(await sumRes.json());
      } else {
        failures.push(`account (HTTP ${sumRes.status})`);
      }
      if (posRes.ok) {
        setPositions(await posRes.json());
      } else {
        failures.push(`positions (HTTP ${posRes.status})`);
      }
      if (ordRes.ok) {
        setOrders(await ordRes.json());
      } else {
        failures.push(`orders (HTTP ${ordRes.status})`);
      }
      setError(failures.length ? `IBKR read failed — ${failures.join(', ')}` : null);
    } catch {
      setError('IBKR account/positions/orders fetch failed — retrying');
    } finally {
      setLoading(false);
    }
  }, [connected]);

  useEffect(() => {
    if (!connected) {
      setSummary(null);
      setPositions([]);
      setOrders([]);
      setError(null);
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

  return { summary, positions, orders, loading, error, refresh };
}
