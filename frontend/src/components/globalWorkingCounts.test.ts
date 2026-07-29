import { describe, expect, it } from 'vitest';
import type { IbkrOrder } from '../ibkr/types';
import { globalWorkingCounts, workingOrderSymbols } from './globalWorkingCounts';

function order(partial: Partial<IbkrOrder> & Pick<IbkrOrder, 'order_id' | 'symbol' | 'status'>): IbkrOrder {
  return {
    side: 'BUY',
    qty: 10,
    order_type: 'LMT',
    limit_price: 1,
    ...partial,
  };
}

describe('globalWorkingCounts', () => {
  it('counts working, filled, and canceled/failed separately', () => {
    const working = [order({ order_id: 1, symbol: 'AAPL', status: 'Submitted' })];
    const closed = [
      order({ order_id: 2, symbol: 'AAPL', status: 'Filled', filled_qty: 10 }),
      order({ order_id: 3, symbol: 'MSFT', status: 'Cancelled', filled_qty: 0 }),
      order({ order_id: 4, symbol: 'TSLA', status: 'Inactive', filled_qty: 0 }),
    ];
    expect(globalWorkingCounts(working, closed)).toEqual({
      working: 1,
      filledToday: 1,
      canceledFailed: 2,
    });
  });

  it('lists unique working symbols for cancel-all', () => {
    expect(
      workingOrderSymbols([
        order({ order_id: 1, symbol: 'aapl', status: 'Submitted' }),
        order({ order_id: 2, symbol: 'AAPL', status: 'Submitted' }),
        order({ order_id: 3, symbol: 'MSFT', status: 'PreSubmitted' }),
      ]),
    ).toEqual(['AAPL', 'MSFT']);
  });
});
