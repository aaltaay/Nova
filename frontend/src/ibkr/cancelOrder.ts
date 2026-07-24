import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  clientTimingHeaders,
  parseTimedExecutionResponse,
  type BrowserExecutionTiming,
} from '../execution_latency';
import { alertApp } from '../ux';

export interface CancelOrderResult {
  ok: boolean;
  error: string | null;
  httpOk: boolean;
  httpStatus: number;
}

export async function cancelIbkrOrder(
  orderId: number,
  timing: BrowserExecutionTiming = beginBrowserExecutionTiming('cancel_order'),
): Promise<CancelOrderResult> {
  try {
    const response = await novaFetch(
      `${API_BASE_URL}/api/ibkr/order/${orderId}`,
      {
        method: 'DELETE',
        headers: clientTimingHeaders(timing),
      },
    );
    const body = await parseTimedExecutionResponse<{
      ok?: boolean;
      error?: string | null;
    }>(response, timing);
    return {
      ok: response.ok && body.ok !== false,
      error: body.error ?? null,
      httpOk: response.ok,
      httpStatus: response.status,
    };
  } catch (error) {
    timing.complete(false);
    throw error;
  }
}

function cancelResultError(result: CancelOrderResult): string | null {
  if (!result.httpOk) {
    return result.error ?? `Cancel failed (HTTP ${result.httpStatus})`;
  }
  return result.ok ? null : result.error ?? 'Cancel was rejected';
}

export async function cancelIbkrOrderWithFeedback(
  orderId: number,
  refresh: () => void,
): Promise<boolean> {
  const timing = beginBrowserExecutionTiming(
    'cancel_order',
    captureBrowserAction('user_action'),
  );
  try {
    const result = await cancelIbkrOrder(orderId, timing);
    const error = cancelResultError(result);
    if (!error) return true;
    await alertApp({ title: 'Cancel failed', message: error, tone: 'danger' });
    return false;
  } catch (error) {
    await alertApp({
      title: 'Cancel failed',
      message: error instanceof Error
        ? error.message
        : 'Network error cancelling order',
      tone: 'danger',
    });
    return false;
  } finally {
    // Keep the existing account poll as recovery even after a visible failure.
    refresh();
  }
}
