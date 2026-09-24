/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  NOVA_ACTION_ACCOUNT_ERROR_MESSAGE,
  NOVA_ACTION_KINDS,
  WHY_GATEWAY_NOT_CONNECTED,
  type NovaActionKind,
} from '../constants';
import { spendLockReason } from '../ibkr/spendLock';
import type { NovaActionRecord } from './novaActionTypes';
import { runNovaAction, type NovaActionRuntime } from './runNovaAction';

const placeIbkrOrder = vi.fn();
const cancelAllOrdersForSymbol = vi.fn();
const cancelAllWorkingOrders = vi.fn();
const countOpenWorkingOrders = vi.fn();

vi.mock('../ibkr/placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
  cancelAllOrdersForSymbol: (...args: unknown[]) => cancelAllOrdersForSymbol(...args),
  cancelAllWorkingOrders: (...args: unknown[]) => cancelAllWorkingOrders(...args),
  countOpenWorkingOrders: (...args: unknown[]) => countOpenWorkingOrders(...args),
}));

vi.mock('../ibkr/placeConfirmPrefs', () => ({
  readSkipPlaceConfirm: () => false,
}));

// The backend arm latch as the desk reads it (`/api/ibkr/status.armed`).
const latch = vi.hoisted(() => ({ armed: true }));

vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => latch.armed,
}));

vi.mock('../ibkr/extendedSession', () => ({
  shouldUseOutsideRth: (flag?: boolean | null) => Boolean(flag),
  flattenNeedsOutsideRth: () => false,
  resolveFillSessionKind: () => 'rth',
}));

vi.mock('../execution_latency', () => ({
  captureBrowserAction: () => ({}),
  beginBrowserExecutionTiming: () => ({}),
}));

function action(partial: Partial<NovaActionRecord> & Pick<NovaActionRecord, 'kind'>): NovaActionRecord {
  return {
    id: 't',
    name: 't',
    key: { label: 'Ctrl+1', key: '1', ctrl: true },
    params: {},
    enabled: true,
    showButton: true,
    ...partial,
  };
}

function runtime(partial: Partial<NovaActionRuntime> = {}): NovaActionRuntime {
  return {
    symbol: 'AAPL',
    connected: true,
    spendStatus: 'paper_armed',
    accountMode: 'paper',
    position: {
      symbol: 'AAPL',
      qty: 4,
      market_price: 10,
      market_value: 40,
      avg_cost: 1,
      unrealized_pnl: 0,
      realized_pnl: 0,
    },
    topOfBook: {
      symbol: 'AAPL',
      bid: 10,
      ask: 10.05,
      depthSubscribed: true,
    },
    requestConfirm: async () => true,
    ...partial,
  };
}

describe('runNovaAction Webull kinds', () => {
  beforeEach(() => {
    placeIbkrOrder.mockReset();
    cancelAllWorkingOrders.mockReset();
    countOpenWorkingOrders.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 9, error: null });
    cancelAllWorkingOrders.mockResolvedValue({
      ok: true,
      cancelled: [1, 2],
      failed: [],
      error: null,
    });
    countOpenWorkingOrders.mockResolvedValue(2);
  });

  it('buy_market places BUY 1 MKT without short_entry', async () => {
    const res = await runNovaAction(
      action({ kind: 'buy_market', params: { shares: 1 } }),
      runtime(),
    );
    expect(res.ok).toBe(true);
    expect(placeIbkrOrder).toHaveBeenCalledOnce();
    const payload = placeIbkrOrder.mock.calls[0][0];
    expect(payload).toMatchObject({
      symbol: 'AAPL',
      side: 'BUY',
      qty: 1,
      order_type: 'MKT',
    });
    expect(payload.short_entry).toBeUndefined();
  });

  it('stamps one idempotency key per invocation (D-011)', async () => {
    const buy = action({ kind: 'buy_market', params: { shares: 1 } });
    await runNovaAction(buy, runtime());
    await runNovaAction(buy, runtime());
    const [first, second] = placeIbkrOrder.mock.calls.map((call) => call[1]);
    expect(first).toMatch(/^nova_action:buy_market:/);
    expect(second).not.toBe(first);
  });

  it('preserves verification reason and order context for the global dialog', async () => {
    placeIbkrOrder.mockResolvedValue({
      ok: false,
      order_id: 96902,
      error: 'Order was not placed. IBKR requires Client Portal verification.',
      reason_code: 'IBKR_VERIFICATION_REQUIRED',
      mode: 'live',
    });

    const res = await runNovaAction(
      action({ kind: 'buy_market', params: { shares: 1 } }),
      runtime({ accountMode: 'live', spendStatus: 'live_armed' }),
    );

    expect(res).toMatchObject({
      ok: false,
      reasonCode: 'IBKR_VERIFICATION_REQUIRED',
      order: { symbol: 'AAPL', side: 'BUY', qty: 1, mode: 'LIVE' },
    });
  });

  it('sell_pos_pct_ask refuses short/flat and sells floor of long', async () => {
    const shortRes = await runNovaAction(
      action({ kind: 'sell_pos_pct_ask', params: { percent: 50 } }),
      runtime({
        position: {
          symbol: 'AAPL',
          qty: -4,
          market_price: 10,
          market_value: -40,
          avg_cost: 1,
          unrealized_pnl: 0,
          realized_pnl: 0,
        },
      }),
    );
    expect(shortRes.ok).toBe(false);
    expect(placeIbkrOrder).not.toHaveBeenCalled();

    const ok = await runNovaAction(
      action({ kind: 'sell_pos_pct_ask', params: { percent: 25, offsetDollars: 0 } }),
      runtime(),
    );
    expect(ok.ok).toBe(true);
    const payload = placeIbkrOrder.mock.calls[0][0];
    expect(payload).toMatchObject({
      side: 'SELL',
      qty: 1,
      order_type: 'LMT',
      limit_price: 10.05,
    });
    expect(payload.short_entry).toBeUndefined();
  });

  it('cancel_all_orders works without an open symbol', async () => {
    const res = await runNovaAction(
      action({ kind: 'cancel_all_orders' }),
      runtime({ symbol: null }),
    );
    expect(res.ok).toBe(true);
    expect(res.text).toMatch(/Cancelled 2/);
    expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
  });

  it('buy Ask+0.05 / sell Bid-0.05 place 1-share EH limits', async () => {
    const buy = await runNovaAction(
      action({
        kind: 'buy_limit_ask_offset',
        params: { shares: 1, offsetDollars: 0.05, outsideRth: true },
      }),
      runtime(),
    );
    expect(buy.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      symbol: 'AAPL',
      side: 'BUY',
      qty: 1,
      order_type: 'LMT',
      limit_price: 10.1,
      outside_rth: true,
    });

    placeIbkrOrder.mockClear();
    const sell = await runNovaAction(
      action({
        kind: 'sell_limit_bid_offset',
        params: { shares: 1, offsetDollars: 0.05, outsideRth: true },
      }),
      runtime(),
    );
    expect(sell.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      side: 'SELL',
      qty: 1,
      order_type: 'LMT',
      limit_price: 9.95,
      outside_rth: true,
    });
    expect(placeIbkrOrder.mock.calls[0][0].short_entry).toBeUndefined();

    placeIbkrOrder.mockClear();
    const sellAsk = await runNovaAction(
      action({
        kind: 'sell_limit_ask_offset',
        params: { shares: 1, offsetDollars: 0.05, outsideRth: true },
      }),
      runtime(),
    );
    expect(sellAsk.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      side: 'SELL',
      qty: 1,
      order_type: 'LMT',
      limit_price: 10.1,
      outside_rth: true,
    });
  });

  it('sell without L2 fails loud', async () => {
    const res = await runNovaAction(
      action({ kind: 'sell_pos_pct_bid_offset', params: { percent: 50, offsetDollars: 0.03 } }),
      runtime({ topOfBook: null }),
    );
    expect(res.ok).toBe(false);
    expect(res.text).toMatch(/L2/i);
    expect(placeIbkrOrder).not.toHaveBeenCalled();
  });
});

describe('runNovaAction whole-position exits (QA R32)', () => {
  beforeEach(() => {
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 9, error: null });
  });

  it('exit_pos sends the whole position as a flatten, never a manual exit', async () => {
    const res = await runNovaAction(action({ kind: 'exit_pos' }), runtime());
    expect(res.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      symbol: 'AAPL', side: 'SELL', qty: 4, intent: 'flatten',
    });
  });

  it('a partial exit is not a flatten', async () => {
    await runNovaAction(action({ kind: 'exit_pos_pct', params: { percent: 50 } }), runtime());
    expect(placeIbkrOrder.mock.calls[0][0].intent).toBeUndefined();
  });
});

describe('disarmed desk (#548, ADR 018 decision 4)', () => {
  // The kinds the backend's arm latch never holds: cancels, and the
  // whole-position exits sent as `intent: "flatten"`.
  const PROTECTIVE: NovaActionKind[] = ['cancel_symbol', 'cancel_all_orders', 'exit_pos', 'cancel_and_exit'];
  // Every other kind -- a new one included -- is an ordinary manual order.
  const OPENING = NOVA_ACTION_KINDS.filter((kind) => !PROTECTIVE.includes(kind));

  function nothingSent() {
    expect(placeIbkrOrder).not.toHaveBeenCalled();
    expect(cancelAllOrdersForSymbol).not.toHaveBeenCalled();
    expect(cancelAllWorkingOrders).not.toHaveBeenCalled();
  }

  beforeEach(() => {
    latch.armed = false;
    placeIbkrOrder.mockReset();
    cancelAllOrdersForSymbol.mockReset();
    cancelAllWorkingOrders.mockReset();
    countOpenWorkingOrders.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 11, error: null });
    cancelAllOrdersForSymbol.mockResolvedValue({ ok: true, cancelled: [7], failed: [], error: null });
    cancelAllWorkingOrders.mockResolvedValue({ ok: true, cancelled: [7, 8], failed: [], error: null });
    countOpenWorkingOrders.mockResolvedValue(2);
  });

  afterEach(() => {
    latch.armed = true;
  });

  it('knows every opening or manual kind it refuses', () => {
    expect(OPENING).toEqual(expect.arrayContaining([
      'buy_market',
      'buy_limit_ask_offset',
      'sell_limit_bid_offset',
      'sell_limit_ask_offset',
      'sell_pos_pct_ask',
      'sell_pos_pct_bid_offset',
      'exit_pos_pct',
    ]));
  });

  describe.each(['paper', 'live'])('on %s', (accountMode) => {
    const disarmed = (partial: Partial<NovaActionRuntime> = {}) =>
      runtime({ accountMode, spendStatus: 'locked_disarmed', ...partial });

    it('exit_pos flattens the whole position without arming', async () => {
      const res = await runNovaAction(action({ kind: 'exit_pos' }), disarmed());
      expect(res.ok).toBe(true);
      expect(placeIbkrOrder).toHaveBeenCalledOnce();
      expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
        symbol: 'AAPL', side: 'SELL', qty: 4, intent: 'flatten',
      });
      expect(latch.armed).toBe(false);
    });

    it('cancel_and_exit cancels the symbol, then flattens', async () => {
      const res = await runNovaAction(action({ kind: 'cancel_and_exit' }), disarmed());
      expect(res.ok).toBe(true);
      expect(cancelAllOrdersForSymbol).toHaveBeenCalledOnce();
      expect(cancelAllOrdersForSymbol.mock.calls[0][0]).toBe('AAPL');
      expect(placeIbkrOrder).toHaveBeenCalledOnce();
      expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
        symbol: 'AAPL', side: 'SELL', qty: 4, intent: 'flatten',
      });
      expect(cancelAllOrdersForSymbol.mock.invocationCallOrder[0])
        .toBeLessThan(placeIbkrOrder.mock.invocationCallOrder[0]);
    });

    it('cancel_symbol cancels the symbol', async () => {
      const res = await runNovaAction(action({ kind: 'cancel_symbol' }), disarmed());
      expect(res).toMatchObject({ ok: true, text: 'Cancelled 1 order(s) for AAPL' });
      expect(cancelAllOrdersForSymbol).toHaveBeenCalledOnce();
      expect(cancelAllOrdersForSymbol.mock.calls[0][0]).toBe('AAPL');
      expect(placeIbkrOrder).not.toHaveBeenCalled();
    });

    it('cancel_all_orders cancels every working order', async () => {
      const res = await runNovaAction(action({ kind: 'cancel_all_orders' }), disarmed({ symbol: null }));
      expect(res).toMatchObject({ ok: true, text: 'Cancelled 2 order(s) (all symbols)' });
      expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
      expect(placeIbkrOrder).not.toHaveBeenCalled();
    });

    it.each(OPENING)('%s is refused: the padlock holds it', async (kind) => {
      const res = await runNovaAction(
        action({ kind, params: { shares: 1, percent: 50, offsetDollars: 0.05 } }),
        disarmed(),
      );
      expect(res.ok).toBe(false);
      expect(res.text).toMatch(/disarmed/i);
      nothingSent();
    });

    it('a disarmed exit_pos still asks to confirm, and a No sends nothing', async () => {
      const requestConfirm = vi.fn(async (_summary: string) => false);
      const res = await runNovaAction(action({ kind: 'exit_pos' }), disarmed({ requestConfirm }));
      expect(requestConfirm).toHaveBeenCalledOnce();
      expect(requestConfirm.mock.calls[0][0]).toMatch(/SELL 4 AAPL/);
      expect(res).toMatchObject({ ok: false, text: 'Order cancelled' });
      nothingSent();
    });

    it('a failed account read still holds both flattens, before any cancel', async () => {
      for (const kind of ['exit_pos', 'cancel_and_exit'] as const) {
        const res = await runNovaAction(action({ kind }), disarmed({ accountError: 'poll failed' }));
        expect(res).toMatchObject({ ok: false, text: NOVA_ACTION_ACCOUNT_ERROR_MESSAGE });
      }
      nothingSent();
    });

    it.each(['locked', 'locked_live_unconfirmed', 'locked_account_unconfirmed', undefined])(
      'the %s lock holds the flattens -- the backend refuses them too -- but not the cancels',
      async (spendStatus) => {
        const locked = (partial: Partial<NovaActionRuntime> = {}) =>
          runtime({ accountMode, ...partial, spendStatus });
        for (const kind of ['exit_pos', 'cancel_and_exit'] as const) {
          const res = await runNovaAction(action({ kind }), locked());
          expect(res).toEqual({ ok: false, text: spendLockReason(spendStatus) });
        }
        // cancel_and_exit is refused before it cancels: no stop is pulled
        // from a position the desk then cannot flatten.
        nothingSent();

        expect((await runNovaAction(action({ kind: 'cancel_symbol' }), locked())).ok).toBe(true);
        expect(cancelAllOrdersForSymbol).toHaveBeenCalledOnce();
        expect((await runNovaAction(action({ kind: 'cancel_all_orders' }), locked())).ok).toBe(true);
        expect(cancelAllWorkingOrders).toHaveBeenCalledOnce();
        expect(placeIbkrOrder).not.toHaveBeenCalled();
      },
    );

    it.each(PROTECTIVE)('%s is refused with no Gateway, and calls nothing', async (kind) => {
      const res = await runNovaAction(action({ kind }), disarmed({ connected: false }));
      expect(res).toEqual({ ok: false, text: WHY_GATEWAY_NOT_CONNECTED });
      nothingSent();
      expect(countOpenWorkingOrders).not.toHaveBeenCalled();
    });
  });
});

