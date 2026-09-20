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
import { SAMPLE_IBKR_ACCOUNT_STATE } from '../sample_data/sampleAccount';
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

// The sample snapshot is a fixture and lives with the other sample fixtures
// (#357). Re-exported so existing importers keep their path.
export { SAMPLE_IBKR_ACCOUNT_STATE };

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
