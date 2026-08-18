import { describe, expect, it } from 'vitest';
import { createDefaultNovaActions } from './novaActionDefaults';

describe('createDefaultNovaActions', () => {
  it('includes cancel, panic cancel+flatten, exit, Ask/Bid, and Webull quick set', () => {
    const actions = createDefaultNovaActions();
    const kinds = new Set(actions.map((a) => a.kind));
    expect(kinds.has('cancel_symbol')).toBe(true);
    expect(kinds.has('cancel_and_exit')).toBe(true);
    expect(kinds.has('cancel_all_orders')).toBe(true);
    expect(kinds.has('exit_pos')).toBe(true);
    expect(kinds.has('exit_pos_pct')).toBe(true);
    expect(kinds.has('buy_market')).toBe(true);
    expect(kinds.has('buy_limit_ask_offset')).toBe(true);
    expect(kinds.has('sell_limit_bid_offset')).toBe(true);
    expect(kinds.has('sell_limit_ask_offset')).toBe(true);
    expect(kinds.has('sell_pos_pct_ask')).toBe(true);
    expect(kinds.has('sell_pos_pct_bid_offset')).toBe(true);
    const buy1 = actions.find((a) => a.id === 'nova-wb-buy-1');
    expect(buy1?.params.shares).toBe(1);
    expect(buy1?.key.label).toMatch(/Ctrl\+1/i);
    const ask = actions.find((a) => a.id === 'nova-buy-ask');
    const bid = actions.find((a) => a.id === 'nova-sell-bid');
    expect(ask?.key.label).toBe('F1');
    expect(ask?.params).toMatchObject({
      shares: 1,
      offsetDollars: 0.05,
      outsideRth: true,
    });
    expect(bid?.key.label).toBe('F2');
    expect(bid?.params).toMatchObject({
      shares: 1,
      offsetDollars: 0.05,
      outsideRth: true,
    });
    const sellAsk = actions.find((a) => a.id === 'nova-sell-ask');
    expect(sellAsk?.key.label).toBe('F5');
    expect(sellAsk?.params).toMatchObject({
      shares: 1,
      offsetDollars: 0.05,
      outsideRth: true,
    });
  });

  it('marks cancel / cancel+flatten / primary exits as showButton', () => {
    const actions = createDefaultNovaActions();
    const cancel = actions.find((a) => a.kind === 'cancel_symbol');
    const panic = actions.find((a) => a.kind === 'cancel_and_exit');
    expect(cancel?.showButton).toBe(true);
    expect(cancel?.enabled).toBe(true);
    expect(panic?.showButton).toBe(true);
    expect(panic?.key.label).toMatch(/Ctrl\+Shift\+Backspace/i);
  });
});

