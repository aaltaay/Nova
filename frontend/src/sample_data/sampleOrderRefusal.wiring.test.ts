/**
 * @vitest-environment jsdom
 *
 * #357: the sample desk must not reach the network for any order mutation.
 * Asserted at the transport boundary (novaFetch), because that is the only
 * place a fabricated sample order id could ever leave the browser.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { novaFetch } from '../api/novaFetch';
import type { BrowserExecutionTiming } from '../execution_latency';
import { cancelIbkrOrder } from '../ibkr/cancelOrder';
import {
  cancelAllOrdersForSymbol,
  cancelAllWorkingOrders,
  placeIbkrOrder,
} from '../ibkr/placeOrder';
import { SAMPLE_ORDER_REFUSAL } from './sampleCopy';

vi.mock('../api/novaFetch', () => ({
  novaFetch: vi.fn(),
}));

vi.mock('../ux', () => ({
  alertApp: vi.fn(),
}));

const PAYLOAD = {
  symbol: 'SMPL',
  side: 'BUY' as const,
  qty: 1,
  order_type: 'MKT' as const,
  outside_rth: false,
};

function timing(): BrowserExecutionTiming {
  return {
    clientTimingAtRequest: vi.fn(() => ({
      action_wall_ms: 1_000,
      action_performance_ms: 10,
      request_wall_ms: 1_020,
      request_performance_ms: 30,
    })),
    complete: vi.fn(),
  };
}

function at(path: string) {
  window.history.replaceState({}, '', path);
}

describe('sample desk refuses order mutations', () => {
  beforeEach(() => {
    vi.mocked(novaFetch).mockReset();
  });

  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('refuses placeIbkrOrder without any transport', async () => {
    at('/?view=sample&symbol=SMPL');
    const result = await placeIbkrOrder(PAYLOAD);

    expect(result.ok).toBe(false);
    expect(result.order_id).toBeNull();
    expect(result.error).toBe(SAMPLE_ORDER_REFUSAL);
    expect(result.reason_code).toBe('SAMPLE_VIEW');
    expect(novaFetch).not.toHaveBeenCalled();
  });

  it('closes a caller-supplied timing span exactly once on refusal', async () => {
    at('/?view=sample');
    const span = timing();
    await placeIbkrOrder(PAYLOAD, 'sample-key', { timing: span });

    expect(span.complete).toHaveBeenCalledTimes(1);
    expect(span.complete).toHaveBeenCalledWith(false);
    expect(novaFetch).not.toHaveBeenCalled();
  });

  it('refuses cancelIbkrOrder — the sample preview-row Cancel path', async () => {
    at('/?view=sample&symbol=SMPL');
    const result = await cancelIbkrOrder(123);

    expect(result).toEqual({
      ok: false,
      error: SAMPLE_ORDER_REFUSAL,
      httpOk: false,
      httpStatus: 0,
    });
    expect(novaFetch).not.toHaveBeenCalled();
  });

  it('refuses both bulk cancels by returning, never by throwing', async () => {
    at('/?view=sample');
    // GlobalWorkingMenu and emergencyKill branch on `ok` — a throw would
    // surface as an unhandled rejection instead of a message.
    const perSymbol = await cancelAllOrdersForSymbol('SMPL');
    const all = await cancelAllWorkingOrders();

    for (const result of [perSymbol, all]) {
      expect(result.ok).toBe(false);
      expect(result.cancelled).toEqual([]);
      expect(result.failed).toEqual([]);
      expect(result.error).toBe(SAMPLE_ORDER_REFUSAL);
    }
    expect(novaFetch).not.toHaveBeenCalled();
  });

  it('still places and cancels on every live route', async () => {
    // The dangerous direction: a false positive would silently block real
    // orders. Each near-miss URL must still reach the transport.
    for (const path of ['/', '/?view=stock&symbol=SMPL', '/?view=samples', '/?view=SAMPLE']) {
      at(path);
      vi.mocked(novaFetch).mockReset();
      // A fresh Response per call: a body can only be read once.
      vi.mocked(novaFetch).mockImplementation(async () =>
        new Response(JSON.stringify({ ok: true, order_id: 7, error: null }), {
          status: 200,
        }),
      );

      const placed = await placeIbkrOrder(PAYLOAD, 'live-key');
      expect(placed.ok, `expected a real place at ${path}`).toBe(true);
      expect(novaFetch, `expected transport at ${path}`).toHaveBeenCalledTimes(1);

      await cancelIbkrOrder(123);
      expect(novaFetch).toHaveBeenCalledTimes(2);
    }
  });
});
