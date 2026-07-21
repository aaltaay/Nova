import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { IbkrAccountSummary, IbkrPosition, IbkrOrder } from './types';

interface AccountState {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  loading: boolean;
  /** Set when the last poll failed to read positions/orders — positions and
   * orders above are the last-good values, not an honest "flat" read. */
  error: string | null;
  refresh: () => void;
}

const SAMPLE_SUMMARY: IbkrAccountSummary = {
  connected: true,
  mode: 'paper',
  NetLiquidation: 100_000,
  BuyingPower: 50_000,
};

/** Polls account summary, positions and open orders every 5 s when connected. */
export function useIbkrAccount(connected: boolean): AccountState {
  const sample = useSampleDataOptional();
  const [summary, setSummary] = useState<IbkrAccountSummary | null>(null);
  const [positions, setPositions] = useState<IbkrPosition[]>([]);
  const [orders, setOrders] = useState<IbkrOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (sample || !connected) return;
    setLoading(true);
    try {
      const [sumRes, posRes, ordRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/ibkr/account`),
        fetch(`${API_BASE_URL}/api/ibkr/positions`),
        fetch(`${API_BASE_URL}/api/ibkr/orders`),
      ]);
      // A non-OK account/positions/orders read is a transport failure, not an
      // honest "flat account" — keep the last-good rows and surface the
      // failure instead of wiping the panel to []. Flatten/exit gates on error.
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
    } catch (err) {
      console.error('[Nova] IBKR account/positions/orders poll failed', err);
      setError('IBKR account/positions/orders fetch failed — retrying');
    } finally {
      setLoading(false);
    }
  }, [sample, connected]);

  useEffect(() => {
    if (sample) return;
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
  }, [sample, connected, refresh]);

  if (sample) {
    return {
      summary: SAMPLE_SUMMARY,
      positions: [],
      orders: [],
      loading: false,
      error: null,
      refresh: () => {},
    };
  }

  return { summary, positions, orders, loading, error, refresh };
}
