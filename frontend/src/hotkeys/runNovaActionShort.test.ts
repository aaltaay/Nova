/**
 * The Short and Cover hotkeys (ADR 048, #778 step 3): a short always carries its buy stop, Nova never flips,
 * and "Cover all" is the protective flatten of a short.
 *
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SHORT_HOTKEY_NO_SHORT, SHORT_WHY_LONG } from '../constantGroups/short_ticket';
import type { NovaActionRecord } from './novaActionTypes';
import { runNovaAction, type NovaActionRuntime } from './runNovaAction';
import { planShortHotkey } from './runNovaActionShort';

const placeIbkrOrder = vi.fn();
vi.mock('../ibkr/placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
  cancelAllOrdersForSymbol: vi.fn(),
  cancelAllWorkingOrders: vi.fn(),
  countOpenWorkingOrders: vi.fn(),
}));
vi.mock('../ibkr/placeConfirmPrefs', () => ({ readSkipPlaceConfirm: () => true }));
const latch = vi.hoisted(() => ({ armed: true }));
vi.mock('../ibkr/ticketUnlock', () => ({ readTicketSessionUnlocked: () => latch.armed }));
vi.mock('../execution_latency', () => ({
  captureBrowserAction: () => ({}),
  beginBrowserExecutionTiming: () => ({}),
}));
vi.mock('../ibkr/marketOutsideRth', async (orig) => ({
  ...(await orig<typeof import('../ibkr/marketOutsideRth')>()),
  // Regular hours, so "Cover all" plans a market order.
  venueClockNow: () => new Date('2026-10-07T14:00:00Z'),
}));

function action(partial: Partial<NovaActionRecord> & Pick<NovaActionRecord, 'kind'>): NovaActionRecord {
  return {
    id: 't', name: 't', key: { label: '', key: '' }, params: {}, enabled: true, showButton: true, ...partial,
  };
}

function runtime(qty: number, partial: Partial<NovaActionRuntime> = {}): NovaActionRuntime {
  return {
    symbol: 'RDYN',
    connected: true,
    spendStatus: 'paper_armed',
    accountMode: 'paper',
    position: qty === 0 ? null : {
      symbol: 'RDYN', qty, market_price: 5.8, market_value: qty * 5.8, avg_cost: 5.77, unrealized_pnl: 0, realized_pnl: 0,
    },
    topOfBook: { symbol: 'RDYN', bid: 5.79, ask: 5.8, depthSubscribed: true },
    ...partial,
  };
}

describe('Short / Cover hotkeys (ADR 048)', () => {
  beforeEach(() => {
    localStorage.clear();
    latch.armed = true;
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 31, error: null });
  });

  it('plans a short a cent over the bid by default, with its buy stop the venue offset over the limit', () => {
    expect(planShortHotkey(action({ kind: 'short_limit_bid_offset' }), { bid: 5.79, ask: 5.8 }))
      .toEqual({ limit: 5.8, stop: 5.9, base: 5.79 });
    expect(planShortHotkey(
      action({ kind: 'short_limit_ask_offset', params: { offsetDollars: -0.01, stopOffsetDollars: 0.12 } }),
      { bid: 5.79, ask: 5.85 },
    )).toEqual({ limit: 5.84, stop: 5.96, base: 5.85 });
    expect(planShortHotkey(action({ kind: 'short_limit_bid_offset' }), { bid: null, ask: 5.8 })).toHaveProperty('error');
  });

  it('SS1 Bid+1 from flat sends a short entry with its buy stop, in regular hours only', async () => {
    const res = await runNovaAction(
      action({ kind: 'short_limit_bid_offset', params: { shares: 1, offsetDollars: 0.01, stopOffsetDollars: 0.1 } }),
      runtime(0),
    );
    expect(res.ok).toBe(true);
    expect(placeIbkrOrder).toHaveBeenCalledOnce();
    expect(placeIbkrOrder.mock.calls[0][0]).toEqual({
      symbol: 'RDYN', side: 'SELL', qty: 1, order_type: 'LMT', outside_rth: false,
      limit_price: 5.8, short_entry: true, stop_loss_price: 5.9,
    });
  });

  it('a Short while long is refused before anything is sent: Nova never flips', async () => {
    const res = await runNovaAction(action({ kind: 'short_limit_bid_offset' }), runtime(100));
    expect(res).toEqual({ ok: false, text: SHORT_WHY_LONG('RDYN') });
    expect(placeIbkrOrder).not.toHaveBeenCalled();
  });

  it('a Short is an opening order: the padlock holds it', async () => {
    latch.armed = false;
    const res = await runNovaAction(action({ kind: 'short_limit_bid_offset' }), runtime(0, { spendStatus: 'locked_disarmed' }));
    expect(res.ok).toBe(false);
    expect(placeIbkrOrder).not.toHaveBeenCalled();
  });

  it('Cover all buys the whole short back through the protective flatten, padlock or not', async () => {
    latch.armed = false;
    const res = await runNovaAction(action({ kind: 'cover_pos' }), runtime(-416, { spendStatus: 'locked_disarmed' }));
    expect(res.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({ symbol: 'RDYN', side: 'BUY', qty: 416, intent: 'flatten' });
  });

  it('a Cover with no short is refused with its reason', async () => {
    for (const kind of ['cover_pos', 'cover_limit_ask_offset'] as const) {
      const res = await runNovaAction(action({ kind }), runtime(100));
      expect(res).toEqual({ ok: false, text: SHORT_HOTKEY_NO_SHORT('RDYN') });
    }
    expect(placeIbkrOrder).not.toHaveBeenCalled();
  });

  it('Cover at Ask + offset buys the whole short back with a limit', async () => {
    const res = await runNovaAction(action({ kind: 'cover_limit_ask_offset', params: { offsetDollars: 0.03 } }), runtime(-200));
    expect(res.ok).toBe(true);
    expect(placeIbkrOrder.mock.calls[0][0]).toEqual({
      symbol: 'RDYN', side: 'BUY', qty: 200, order_type: 'LMT', outside_rth: false, limit_price: 5.83,
    });
  });
});
