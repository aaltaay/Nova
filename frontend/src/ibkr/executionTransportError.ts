/**
 * Map a thrown fetch/parse failure to ticket copy.
 * "Network error" hid IB-loop stalls (ledger left at validated, no broker send).
 */
import {
  EXECUTION_TRANSPORT_FAILED_MESSAGE,
  EXECUTION_TRANSPORT_TIMEOUT_MESSAGE,
  EXECUTION_TRANSPORT_UNREACHABLE_MESSAGE,
} from '../constantGroups/features';

export function executionTransportError(error: unknown): string {
  const name = error instanceof Error ? error.name : '';
  const msg = error instanceof Error ? error.message : String(error ?? '');
  if (name === 'AbortError' || /aborted|timeout/i.test(msg)) {
    return EXECUTION_TRANSPORT_TIMEOUT_MESSAGE;
  }
  if (/failed to fetch|networkerror|load failed/i.test(msg)) {
    return EXECUTION_TRANSPORT_UNREACHABLE_MESSAGE;
  }
  return msg.trim() || EXECUTION_TRANSPORT_FAILED_MESSAGE;
}
