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
  shouldUseOutsideRth: () => false,
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
