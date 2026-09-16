/**
 * App-wide IBKR account / positions / orders poller.
 * Account cluster (summary + positions) ticks at IBKR_ACCOUNT_POLL_MS (<=1s).
 * Orders / closed stay on IBKR_ORDERS_POLL_MS so we do not hammer IBKR.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { API_BASE_URL, IBKR_ACCOUNT_POLL_MS, IBKR_ORDERS_POLL_MS } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { lastKnownAsOfMessage } from './disconnectCopy';
import { fetchAccountCluster, fetchOrdersCluster } from './ibkrAccountFetch';
import type { IbkrAccountSummary, IbkrOrder, IbkrPosition } from './types';

export interface IbkrAccountState {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  /** Session terminal orders -- chart fill arrows. Optional on older fixtures. */
  closedOrders?: IbkrOrder[];
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
  // Sample desk is a margin paper fixture so Side can show Short (#184).
  // Live accounts use IBKR AccountType only -- never invent Margin.
  AccountType: 'MARGIN',
};

export const SAMPLE_IBKR_ACCOUNT_STATE: IbkrAccountState = {
  summary: SAMPLE_SUMMARY,
  positions: [
    {
      symbol: 'SMPL',
      qty: 200,
      market_price: 4.25,
      market_value: 850,
      avg_cost: 3.1,
      unrealized_pnl: 230,
      realized_pnl: 0,
    },
  ],
  orders: [],
  closedOrders: [],
  loading: false,
  error: null,
  stale: false,
  staleSince: null,
  refresh: () => {},
};

const IbkrAccountContext = createContext<IbkrAccountState | null>(null);

function mergeReadError(accountFails: string[], orderFails: string[]): string | null {
  const failures = [...accountFails, ...orderFails];
  return failures.length ? `IBKR read failed -- ${failures.join(', ')}` : null;
}

export function IbkrAccountProvider({ children }: { children: ReactNode }) {
  const sample = useSampleDataOptional();
  const { ibkrConnected } = useWorkspace();
  const [summary, setSummary] = useState<IbkrAccountSummary | null>(null);
  const [positions, setPositions] = useState<IbkrPosition[]>([]);
  const [orders, setOrders] = useState<IbkrOrder[]>([]);
  const [closedOrders, setClosedOrders] = useState<IbkrOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [staleSince, setStaleSince] = useState<number | null>(null);
  const hadSessionRef = useRef(false);
  const accountInflight = useRef(false);
  const ordersInflight = useRef(false);
  const accountFailsRef = useRef<string[]>([]);
  const orderFailsRef = useRef<string[]>([]);

  const publishError = useCallback(() => {
    setError(mergeReadError(accountFailsRef.current, orderFailsRef.current));
  }, []);

  const refreshAccount = useCallback(async () => {
    if (sample || !ibkrConnected || accountInflight.current) return;
    accountInflight.current = true;
    setLoading(true);
    try {
      const snap = await fetchAccountCluster(API_BASE_URL);
      if (snap.summary) setSummary(snap.summary);
      if (snap.positions) setPositions(snap.positions);
      accountFailsRef.current = snap.failures;
      setStale(false);
      setStaleSince(null);
      publishError();
    } catch (err) {
      console.error('[Nova] IBKR account/positions poll failed', err);
      accountFailsRef.current = ['account/positions fetch failed -- retrying'];
      publishError();
    } finally {
      accountInflight.current = false;
      setLoading(false);
    }
  }, [sample, ibkrConnected, publishError]);

  const refreshOrders = useCallback(async () => {
    if (sample || !ibkrConnected || ordersInflight.current) return;
    ordersInflight.current = true;
    try {
      const snap = await fetchOrdersCluster(API_BASE_URL);
      if (snap.orders) setOrders(snap.orders);
      if (snap.closedOrders) setClosedOrders(snap.closedOrders);
      orderFailsRef.current = snap.failures;
      publishError();
    } catch (err) {
      console.error('[Nova] IBKR orders poll failed', err);
      orderFailsRef.current = ['orders fetch failed -- retrying'];
      publishError();
    } finally {
      ordersInflight.current = false;
    }
  }, [sample, ibkrConnected, publishError]);

  const refresh = useCallback(() => {
    void refreshAccount();
    void refreshOrders();
  }, [refreshAccount, refreshOrders]);

  useEffect(() => {
    if (sample) return;
    if (ibkrConnected) {
      hadSessionRef.current = true;
    }
    if (!ibkrConnected) {
      if (!hadSessionRef.current) {
        setLoading(false);
        return;
      }
      const since = Date.now();
      setStale(true);
      setStaleSince(since);
      setError(lastKnownAsOfMessage(since));
      setLoading(false);
      return;
    }

    let active = true;
    const tickAccount = () => {
      if (active) void refreshAccount();
    };
    const tickOrders = () => {
      if (active) void refreshOrders();
    };
    tickAccount();
    tickOrders();
    const accId = setInterval(tickAccount, IBKR_ACCOUNT_POLL_MS);
    const ordId = setInterval(tickOrders, IBKR_ORDERS_POLL_MS);
    return () => {
      active = false;
      clearInterval(accId);
      clearInterval(ordId);
    };
  }, [sample, ibkrConnected, refreshAccount, refreshOrders]);

  const value = useMemo<IbkrAccountState>(() => {
    if (sample) return SAMPLE_IBKR_ACCOUNT_STATE;
    return {
      summary, positions, orders, closedOrders, loading, error, stale, staleSince, refresh,
    };
  }, [sample, summary, positions, orders, closedOrders, loading, error, stale, staleSince, refresh]);

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
