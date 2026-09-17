/**
 * App-wide IBKR account / positions / orders reader.
 * HTTP lives in ibkrAccountPoller (one owner, cross-window leader).
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  configureIbkrAccountPoller,
  getIbkrAccountSnapshot,
  refreshIbkrAccountNow,
  subscribeIbkrAccount,
  type IbkrAccountPollSnap,
} from './ibkrAccountPoller';
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
  // Live desks use stamped account_class / shortSideVisible -- never AccountType=INDIVIDUAL.
  AccountType: 'MARGIN',
  account_class: 'margin',
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

const EMPTY_SNAP: IbkrAccountPollSnap = {
  summary: null,
  positions: [],
  orders: [],
  closedOrders: [],
  loading: false,
  error: null,
  stale: false,
  staleSince: null,
};

function noopSubscribe(_onStoreChange: () => void): () => void {
  return () => {};
}

export function IbkrAccountProvider({ children }: { children: ReactNode }) {
  const sample = useSampleDataOptional();
  const { ibkrConnected } = useWorkspace();

  useEffect(() => {
    configureIbkrAccountPoller({
      connected: ibkrConnected,
      sample: Boolean(sample),
    });
  }, [sample, ibkrConnected]);

  const snap = useSyncExternalStore(
    sample ? noopSubscribe : subscribeIbkrAccount,
    sample ? () => EMPTY_SNAP : getIbkrAccountSnapshot,
    () => EMPTY_SNAP,
  );

  const value = useMemo<IbkrAccountState>(() => {
    if (sample) return SAMPLE_IBKR_ACCOUNT_STATE;
    return {
      ...snap,
      refresh: refreshIbkrAccountNow,
    };
  }, [sample, snap]);

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
