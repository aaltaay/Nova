import { useSyncExternalStore } from 'react';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { SAMPLE_IBKR_STATUS } from '../sample_data/sampleStatus';
import {
  DEFAULT_IBKR_STATUS,
  getIbkrStatusSnapshot,
  refreshIbkrStatusNow,
  subscribeIbkrStatus,
  type IbkrClientStatus,
} from './ibkrStatusPoller';

export type { IbkrClientStatus };
export { refreshIbkrStatusNow };

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
  return SAMPLE_IBKR_STATUS;
}

/**
 * Shared /api/ibkr/status -- one poller, every caller reads the same snapshot.
 * Under SampleDataProvider the sample status, with no subscription; above it
 * (WorkspaceProvider) the poller itself answers the sample status on
 * ?view=sample and makes no request (V4).
 */
export function useIbkrStatus(): IbkrClientStatus {
  const sample = useSampleDataOptional();
  return useSyncExternalStore(
    sample ? noopSubscribe : subscribeIbkrStatus,
    sample ? getSampleSnapshot : getIbkrStatusSnapshot,
    () => EMPTY,
  );
}
