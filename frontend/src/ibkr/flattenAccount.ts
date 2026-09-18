/**
 * Whole-account MKT flatten -- HTTP door for bot.flatten.flatten_account_with_retry.
 * Same market-close path breakers already use (execution source=flatten).
 * Not a second place stack.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { executionTransportError } from './executionTransportError';

export interface FlattenAccountResult {
  ok: boolean;
  error: string | null;
  results?: unknown;
  cancels?: unknown;
  attempt?: number;
}

export async function flattenAccount(): Promise<FlattenAccountResult> {
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
