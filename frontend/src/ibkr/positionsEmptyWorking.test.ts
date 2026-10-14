import { describe, expect, it } from 'vitest';
import { positionsEmptyWorkingLine, workingOrderWords } from './positionsEmptyWorking';
import type { IbkrOrder } from './types';

// GENK, 2026-10-14: "No open positions." while a buy of 1,000 at 2.76 worked for three minutes.
const GENK = {
  order_id: 255, symbol: 'GENK', side: 'BUY', qty: 1000, remaining_qty: 1000, order_type: 'LMT',
  limit_price: 2.76, status: 'Submitted', submitted_at: '2026-10-14T13:25:19.858Z',
} as IbkrOrder;

describe('the Positions empty state while an order works', () => {
  it('names each working order: side, size, symbol, price and since when', () => {
    expect(workingOrderWords(GENK)).toBe('Buy 1,000 GENK LMT 2.76 since 09:25:19 ET');
    expect(positionsEmptyWorkingLine([GENK])).toBe(
      '1 working order: Buy 1,000 GENK LMT 2.76 since 09:25:19 ET. Each becomes a position the moment it fills.',
    );
  });

  it('says a stop, a market order and a part-filled one in their own words', () => {
    const stop = { ...GENK, side: 'SELL', order_type: 'STP', stop_price: 2.2, limit_price: null, remaining_qty: 400 };
    const market = { ...GENK, order_type: 'MKT', limit_price: null, submitted_at: null };
    expect(workingOrderWords(stop as IbkrOrder)).toBe('Sell 400 GENK STP 2.2 since 09:25:19 ET');
    expect(workingOrderWords(market as IbkrOrder)).toBe('Buy 1,000 GENK at market');
    expect(positionsEmptyWorkingLine([GENK, stop as IbkrOrder])).toMatch(/^2 working orders: Buy .*; Sell 400 GENK/);
  });

  it('says nothing more when nothing works', () => {
    expect(positionsEmptyWorkingLine([])).toBeNull();
  });
});
