import { describe, expect, it } from 'vitest';
import { createDefaultNovaActions } from './novaActionDefaults';
import { quickTradeLabelPieces, quickTradeShortLabel, quickTradeTone } from './quickTradeLabel';

describe('quickTradeShortLabel', () => {
  it('builds the mockup labels from the default actions', () => {
    const labels = createDefaultNovaActions()
      .filter((a) => a.showButton)
      .map((a) => quickTradeShortLabel(a.kind, a.params));
    expect(labels).toEqual([
      'Cxl sym',
      'Cxl+Flat',
      'Flatten',
      'Exit 50%',
      'B1 Ask+5',
      'S1 Bid−5',
      'S1 Ask+5',
      'B1 MKT',
      'Cxl all',
      'Sell all',
    ]);
  });

  it('keeps a partial sell honest and rounds the offset to cents', () => {
    expect(quickTradeShortLabel('sell_pos_pct_ask', { percent: 50, offsetDollars: 0 })).toBe('Sell 50%');
    expect(
      quickTradeShortLabel('sell_pos_pct_bid_offset', { percent: 25, offsetDollars: 0.03 }),
    ).toBe('S25% Bid−3');
    expect(quickTradeShortLabel('buy_market', {})).toBe('B MKT');
  });
});

describe('quickTradeLabelPieces (QA D14: a label wraps between words, never inside one)', () => {
  const texts = (label: string) => quickTradeLabelPieces(label).map((p) => (p.spaced ? ` ${p.text}` : p.text));

  it('cuts at spaces and after a "+" that joins two words', () => {
    expect(texts('Cxl sym')).toEqual(['Cxl', ' sym']);
    expect(texts('Cxl+Flat')).toEqual(['Cxl+', 'Flat']);
    expect(texts('Flatten')).toEqual(['Flatten']);
  });

  it('keeps an amount after "+" or "−" with its word', () => {
    expect(texts('B1 Ask+5')).toEqual(['B1', ' Ask+5']);
    expect(texts('S25% Bid−3')).toEqual(['S25%', ' Bid−3']);
  });

  it('puts every default label back together unchanged', () => {
    for (const action of createDefaultNovaActions().filter((a) => a.showButton)) {
      const label = quickTradeShortLabel(action.kind, action.params);
      expect(texts(label).join('')).toBe(label);
    }
  });
});

describe('quickTradeTone', () => {
  it('colours by what the action does: buys, sells, protective exits, cancels', () => {
    expect(quickTradeTone('buy_limit_ask_offset')).toBe('buy');
    expect(quickTradeTone('buy_market')).toBe('buy');
    expect(quickTradeTone('sell_limit_bid_offset')).toBe('sell');
    expect(quickTradeTone('sell_pos_pct_ask')).toBe('sell');
    expect(quickTradeTone('exit_pos')).toBe('protective');
    expect(quickTradeTone('exit_pos_pct')).toBe('protective');
    expect(quickTradeTone('cancel_and_exit')).toBe('protective');
    expect(quickTradeTone('cancel_symbol')).toBe('cancel');
    expect(quickTradeTone('cancel_all_orders')).toBe('cancel');
  });
});
