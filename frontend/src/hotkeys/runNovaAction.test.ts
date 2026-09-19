/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NovaActionRecord } from './novaActionTypes';
import { runNovaAction, type NovaActionRuntime } from './runNovaAction';

const placeIbkrOrder = vi.fn();
const cancelAllWorkingOrders = vi.fn();
const countOpenWorkingOrders = vi.fn();

vi.mock('../ibkr/placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
  cancelAllOrdersForSymbol: vi.fn(),
  cancelAllWorkingOrders: (...args: unknown[]) => cancelAllWorkingOrders(...args),
  countOpenWorkingOrders: (...args: unknown[]) => countOpenWorkingOrders(...args),
}));

vi.mock('../ibkr/placeConfirmPrefs', () => ({
  readSkipPlaceConfirm: () => false,
}));

vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
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
