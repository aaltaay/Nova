/**
 * Account / positions / open-orders reader.
 * Live path reads the shared IbkrAccountProvider poller. Sample path returns
 * fixtures without mounting the provider (SampleShell stays isolated).
 */
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import {
  SAMPLE_IBKR_ACCOUNT_STATE,
  useOptionalIbkrAccountContext,
  type IbkrAccountState,
} from './IbkrAccountContext';

export type { IbkrAccountState as AccountState };

/**
 * @param _connected Kept for call-site compatibility; the shared provider
 *                   already gates on WorkspaceContext.ibkrConnected.
 */
export function useIbkrAccount(_connected: boolean): IbkrAccountState {
  const sample = useSampleDataOptional();
  const ctx = useOptionalIbkrAccountContext();

  if (sample) return SAMPLE_IBKR_ACCOUNT_STATE;

  if (!ctx) {
    throw new Error('useIbkrAccount must be used within IbkrAccountProvider');
  }
  return ctx;
}
