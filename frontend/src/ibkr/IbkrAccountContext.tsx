/**
 * App-wide IBKR account / positions / orders poller.
 * Mount once under WorkspaceProvider so GlobalAppBar, Trader View, and the
 * Account tab share a single 5s poll instead of each owning a loop.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { API_BASE_URL, IBKR_ACCOUNT_POLL_MS } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { lastKnownAsOfMessage } from './disconnectCopy';
import type { IbkrAccountSummary, IbkrOrder, IbkrPosition } from './types';

export interface IbkrAccountState {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  loading: boolean;
  /** Set when the last poll failed -- last-good rows are kept, not wiped. */
  error: string | null;
  /** True after Gateway drops; rows are last-good and must not drive Flatten. */
  stale: boolean;
  staleSince: number | null;
  refresh: () => void;
}

const SAMPLE_SUMMARY: IbkrAccountSummary = {
  connected: true,
  mode: 'paper',
  NetLiquidation: 100_000,
  BuyingPower: 50_000,
};

export const SAMPLE_IBKR_ACCOUNT_STATE: IbkrAccountState = {
  summary: SAMPLE_SUMMARY,
  positions: [],
  orders: [],
  loading: false,
  error: null,
  stale: false,
  staleSince: null,
  refresh: () => {},
};

const IbkrAccountContext = createContext<IbkrAccountState | null>(null);

export function IbkrAccountProvider({ children }: { children: ReactNode }) {
  const sample = useSampleDataOptional();
  const { ibkrConnected } = useWorkspace();
  const [summary, setSummary] = useState<IbkrAccountSummary | null>(null);
  const [positions, setPositions] = useState<IbkrPosition[]>([]);
  const [orders, setOrders] = useState<IbkrOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [staleSince, setStaleSince] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (sample || !ibkrConnected) return;
    setLoading(true);
    try {
      const [sumRes, posRes, ordRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/ibkr/account`),
        fetch(`${API_BASE_URL}/api/ibkr/positions`),
        fetch(`${API_BASE_URL}/api/ibkr/orders`),
      ]);
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
      setError(failures.length ? `IBKR read failed -- ${failures.join(', ')}` : null);
      setStale(false);
      setStaleSince(null);
    } catch (err) {
      console.error('[Nova] IBKR account/positions/orders poll failed', err);
      setError('IBKR account/positions/orders fetch failed -- retrying');
    } finally {
      setLoading(false);
    }
  }, [sample, ibkrConnected]);

  useEffect(() => {
    if (sample) return;
    if (!ibkrConnected) {
      const since = Date.now();
      setStale(true);
      setStaleSince(since);
      setError(lastKnownAsOfMessage(since));
      setLoading(false);
      return;
    }

    let active = true;
    const tick = () => {
      if (active) void refresh();
    };
    tick();
    const id = setInterval(tick, IBKR_ACCOUNT_POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sample, ibkrConnected, refresh]);

  const value = useMemo<IbkrAccountState>(() => {
    if (sample) return SAMPLE_IBKR_ACCOUNT_STATE;
    return { summary, positions, orders, loading, error, stale, staleSince, refresh };
  }, [sample, summary, positions, orders, loading, error, stale, staleSince, refresh]);

  return (
    <IbkrAccountContext.Provider value={value}>{children}</IbkrAccountContext.Provider>
  );
}

/** Prefer this over useIbkrAccount when the consumer is always under the provider. */
export function useIbkrAccountContext(): IbkrAccountState {
  const ctx = useContext(IbkrAccountContext);
  if (!ctx) {
    throw new Error('useIbkrAccountContext must be used within IbkrAccountProvider');
  }
  return ctx;
}

export function useOptionalIbkrAccountContext(): IbkrAccountState | null {
  return useContext(IbkrAccountContext);
}
