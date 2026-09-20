/**
 * Whole-account MKT flatten -- HTTP door for bot.flatten.flatten_account_with_retry.
 * Same market-close path breakers already use (execution source=flatten).
 * Not a second place stack.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { sampleOrderRefusal } from '../sample_data/sampleOrderGuard';
import { executionTransportError } from './executionTransportError';

export interface FlattenAccountResult {
  ok: boolean;
  error: string | null;
  results?: unknown;
  cancels?: unknown;
  attempt?: number;
}

export async function flattenAccount(): Promise<FlattenAccountResult> {
  // A flatten is the most destructive door in this module -- a whole-account
  // MKT liquidation. It must refuse on the sample route for the same reason
  // the cancel doors do, and it must refuse TOGETHER with them: guarding the
  // protective cancel while letting the destructive flatten through would
  // leave resting orders live on an account that was just flattened (#357).
  // runEmergencyKill refuses the whole composite before reaching here; this is
  // the transport-level backstop for any future caller.
  const refusal = sampleOrderRefusal();
  if (refusal) return { ok: false, error: refusal };
  try {
    const response = await novaFetch(`${API_BASE_URL}/api/ibkr/flatten-account`, {
      method: 'POST',
    });
    const data = (await response.json().catch(() => ({}))) as {
      ok?: boolean;
      error?: string | null;
      results?: unknown;
      cancels?: unknown;
      attempt?: number;
      detail?: unknown;
    };
    if (!response.ok) {
      const detail =
        typeof data.detail === 'string'
          ? data.detail
          : typeof data.error === 'string'
            ? data.error
            : `HTTP ${response.status}`;
      return { ok: false, error: detail };
    }
    return {
      ok: data.ok !== false,
      error: data.error ?? null,
      results: data.results,
      cancels: data.cancels,
      attempt: data.attempt,
    };
  } catch (error) {
    return { ok: false, error: executionTransportError(error) };
  }
}
