import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { sampleOrderRefusal } from '../sample_data/sampleOrderGuard';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  clientTimingHeaders,
  parseTimedExecutionResponse,
  type BrowserExecutionTiming,
} from '../execution_latency';
import { alertApp } from '../ux';
import { getIbkrAccountSnapshot } from './ibkrAccountPoller';

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
  // Defence in depth for the fabricated working-order rows (#357). The row
  // Cancel button is already withheld for them -- OrdersTodayView passes
  // `onCancelOrder={usingWorkingSample ? undefined : ...}` and
  // WorkingOrdersPanel renders the button only when that prop exists -- so this
  // guard is not the only thing standing between a preview row and a real
  // DELETE, and must not be described as if it were. It covers hotkeys and any
  // future caller that reaches this door from the ?view=sample URL.
  const refusal = sampleOrderRefusal();
  if (refusal) {
    timing.complete(false);
    return { ok: false, error: refusal, httpOk: false, httpStatus: 0 };
  }
  try {
    // An order id is only meaningful on the venue that issued it (#655): the rows on
    // screen came from this venue, so the backend refuses VENUE_CHANGED if the desk has
    // moved since instead of cancelling that venue's order of the same number.
    const venue = getIbkrAccountSnapshot().venue;
    const query = venue ? `?venue=${encodeURIComponent(venue)}` : '';
    const response = await novaFetch(
      `${API_BASE_URL}/api/ibkr/order/${orderId}${query}`,
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
