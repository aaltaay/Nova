/**
 * QA R21: the Trader's Flatten (the Nova Action exit) plans regular hours from
 * the venue's clock -- the Sim playhead on Sim -- exactly like the ticket's
 * Flatten. On a Sim playhead inside regular hours with a premarket wall clock
 * it used to plan the extended-hours limit, which the practice broker then
 * judged against the playhead.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BrowserActionStamp } from '../execution_latency';
import { simClockResource } from '../sim/simClockResource';
import type { SimClockState } from '../sim/simClockTypes';
import { placeMarketExit } from './runNovaActionPlace';
import type { NovaActionRuntime } from './runNovaActionRuntime';

const placeIbkrOrder = vi.fn();

vi.mock('../ibkr/placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
}));

vi.mock('../execution_latency', () => ({
  beginBrowserExecutionTiming: () => ({}),
}));

const STAMP: BrowserActionStamp = { wallMs: 0, performanceMs: 0, source: 'user_action' };
const confirm = async () => true;

function runtime(accountMode: string): NovaActionRuntime {
  return {
    symbol: 'GRML',
    connected: true,
    spendStatus: 'paper_armed',
    accountMode,
    position: {
      symbol: 'GRML',
      qty: 2,
      market_price: 9.305,
      market_value: 18.61,
      avg_cost: 9,
      unrealized_pnl: 0,
      realized_pnl: 0,
    },
    topOfBook: { symbol: 'GRML', bid: 9.3, ask: 9.31, depthSubscribed: true },
    requestConfirm: confirm,
  };
}

describe('placeMarketExit on the venue clock (QA R21)', () => {
  afterEach(() => {
    vi.useRealTimers();
    simClockResource.setData(null);
    placeIbkrOrder.mockReset();
  });

  it('plans regular hours from the Sim playhead, and from the wall clock on Paper', async () => {
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 5, error: null });
    // Playhead Mon 2026-09-21 13:05 ET (regular hours); wall clock 05:00 ET the next day.
    simClockResource.setData({
      sim: true,
      live_edge: false,
      sim_time_et: '2026-09-21T13:05:00-04:00',
    } as SimClockState);
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-22T09:00:00Z'));

    const sim = await placeMarketExit(runtime('sim'), 'GRML', 'SELL', 2, 'flatten', STAMP, confirm, 'k-sim', 'flatten');
    expect(sim.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      order_type: 'MKT',
      outside_rth: false,
      intent: 'flatten',
    });

    const paper = await placeMarketExit(runtime('paper'), 'GRML', 'SELL', 2, 'flatten', STAMP, confirm, 'k-paper', 'flatten');
    expect(paper.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[1][0]).toMatchObject({
      order_type: 'LMT',
      outside_rth: true,
      limit_price: 9.3,
    });
  });
});
