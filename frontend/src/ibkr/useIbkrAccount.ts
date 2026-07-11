import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { IbkrAccountSummary, IbkrPosition, IbkrOrder } from './types';

interface AccountState {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  loading: boolean;
}

/** Polls account summary, positions and open orders every 5 s when connected. */
export function useIbkrAccount(connected: boolean): AccountState {
  const [state, setState] = useState<AccountState>({
    summary: null,
    positions: [],
    orders: [],
    loading: false,
  });

  useEffect(() => {
    if (!connected) {
      setState({ summary: null, positions: [], orders: [], loading: false });
      return;
    }

    let active = true;

    async function refresh() {
      setState(s => ({ ...s, loading: true }));
      try {
        const [sumRes, posRes, ordRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/ibkr/account`),
          fetch(`${API_BASE_URL}/api/ibkr/positions`),
          fetch(`${API_BASE_URL}/api/ibkr/orders`),
        ]);
        if (active) {
          setState({
            summary: sumRes.ok ? await sumRes.json() : null,
            positions: posRes.ok ? await posRes.json() : [],
            orders: ordRes.ok ? await ordRes.json() : [],
            loading: false,
          });
        }
      } catch {
        if (active) setState(s => ({ ...s, loading: false }));
      }
    }

    refresh();
    const id = setInterval(refresh, 5_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [connected]);

  return state;
}
