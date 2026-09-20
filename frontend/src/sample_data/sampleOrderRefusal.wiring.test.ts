/**
 * @vitest-environment jsdom
 *
 * #357: no order mutation from the sample desk reaches the network.
 *
 * Scope is stated exactly, because an earlier version of this file claimed the
 * four functions it enumerated were "the only place a fabricated sample order
 * id could ever leave the browser" — which was false, and let the whole-account
 * flatten ship unguarded behind a green suite. The order doors under src/ibkr/
 * are placeIbkrOrder, cancelIbkrOrder, cancelAllOrdersForSymbol,
 * cancelAllWorkingOrders and flattenAccount; runEmergencyKill composes two of
 * them plus a bot-session PATCH. All six are asserted below, at the novaFetch
 * boundary, together with the live-route control that proves the guard is not
 * blocking real orders.
 *
 * Non-order endpoints reachable from the sample route (bot controls, settings)
 * are NOT covered by this guard and are not claimed to be.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { novaFetch } from '../api/novaFetch';
import type { BrowserExecutionTiming } from '../execution_latency';
import { cancelIbkrOrder } from '../ibkr/cancelOrder';
import { runEmergencyKill } from '../ibkr/emergencyKill';
import { flattenAccount } from '../ibkr/flattenAccount';
import {
  cancelAllOrdersForSymbol,
  cancelAllWorkingOrders,
  placeIbkrOrder,
} from '../ibkr/placeOrder';
import { SAMPLE_KILL_REFUSAL, SAMPLE_ORDER_REFUSAL } from './sampleCopy';

vi.mock('../api/novaFetch', () => ({
  novaFetch: vi.fn(),
}));

vi.mock('../ux', () => ({
  alertApp: vi.fn(),
}));

// The bot poller refresh is not an order door; stubbing it keeps the live-route
// control's request list to the calls Emergency KILL itself makes.
vi.mock('../bot/botSessionPoller', () => ({
  refreshBotSessionNow: vi.fn(),
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

/** URLs novaFetch was asked for, in call order. */
function requestedUrls(): string[] {
  return vi.mocked(novaFetch).mock.calls.map(([url]) => String(url));
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

  it('refuses cancelIbkrOrder', async () => {
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

  it('refuses flattenAccount — the whole-account MKT liquidation', async () => {
    at('/?view=sample');
    const result = await flattenAccount();

    expect(result).toEqual({ ok: false, error: SAMPLE_ORDER_REFUSAL });
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

      const flattened = await flattenAccount();
      expect(flattened.ok, `expected a real flatten at ${path}`).toBe(true);
      expect(novaFetch).toHaveBeenCalledTimes(3);
    }
  });
});

describe('Emergency KILL on the sample desk refuses as one unit', () => {
  beforeEach(() => {
    vi.mocked(novaFetch).mockReset();
  });

  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('fires no leg at all — not the bot PATCH, not cancel, not flatten', async () => {
    // The defect this replaces: cancel was refused while flatten still POSTed,
    // so the account was market-flattened with its resting orders left live —
    // a state neither master nor a fully-guarded route can produce — while the
    // operator read a refusal dialog.
    at('/?view=sample');

    const result = await runEmergencyKill();

    expect(result.ok).toBe(false);
    expect(result.errors).toEqual([SAMPLE_KILL_REFUSAL]);
    expect(novaFetch).not.toHaveBeenCalled();
  });

  it('tells the operator nothing happened and where a real kill lives', async () => {
    at('/?view=sample&symbol=SMPL');
    const [message] = (await runEmergencyKill()).errors;

    expect(message).toContain('Nova Marketing Sample Data');
    expect(message).toMatch(/nothing was cancelled or flattened/i);
    expect(message).toMatch(/exit the sample desk/i);
    expect(message).not.toMatch(/fake|mock|dummy/i);
  });

  it('still cancels before it flattens on a live route', async () => {
    // Master's behaviour must be untouched off ?view=sample, in that order:
    // cancel-before-flatten is what stops a resting order re-filling after the
    // flatten (emergencyKill.ts module header).
    at('/');
    vi.mocked(novaFetch).mockImplementation(async () =>
      new Response(JSON.stringify({ ok: true, level: 0, cancelled: [], failed: [] }), {
        status: 200,
      }),
    );

    const result = await runEmergencyKill();

    const urls = requestedUrls();
    const cancelAt = urls.findIndex(u => u.includes('/api/ibkr/orders?all_symbols=true'));
    const flattenAt = urls.findIndex(u => u.includes('/api/ibkr/flatten-account'));
    expect(cancelAt, `no cancel-all in ${urls.join(', ')}`).toBeGreaterThanOrEqual(0);
    expect(flattenAt, `no flatten in ${urls.join(', ')}`).toBeGreaterThanOrEqual(0);
    expect(cancelAt).toBeLessThan(flattenAt);
    expect(urls.some(u => u.includes('/bot/session'))).toBe(true);
    expect(result.ok).toBe(true);
  });
});
