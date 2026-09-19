import { useSyncExternalStore } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import {
  DEFAULT_IBKR_STATUS,
  getIbkrStatusSnapshot,
  refreshIbkrStatusNow,
  subscribeIbkrStatus,
  type IbkrClientStatus,
} from './ibkrStatusPoller';

export type { IbkrClientStatus };
export { refreshIbkrStatusNow };

const SAMPLE_STATUS: IbkrClientStatus = {
  enabled: true,
  connected: true,
  transport_connected: true,
  session_reason: 'ok',
  mode: 'paper',
  orders_enabled: true,
  short_enabled: true,
  spend_status: 'paper_armed',
  trading_allowed: true,
  trading_allowed_reason: null,
  market_data_type: 1,
  market_data_delayed: false,
  clientReady: true,
  stale: false,
  staleSince: null,
};

const EMPTY: IbkrClientStatus = {
  ...DEFAULT_IBKR_STATUS,
  clientReady: false,
  stale: false,
  staleSince: null,
};

function noopSubscribe(_onStoreChange: () => void): () => void {
  return () => {};
}

function getSampleSnapshot(): IbkrClientStatus {
  return SAMPLE_STATUS;
}

/** Shared /api/ibkr/status -- one poller, every caller reads the same snapshot. */
export function useIbkrStatus(): IbkrClientStatus {
  const sample = useSampleDataOptional();
  return useSyncExternalStore(
    sample ? noopSubscribe : subscribeIbkrStatus,
    sample ? getSampleSnapshot : getIbkrStatusSnapshot,
    () => EMPTY,
  );
}
