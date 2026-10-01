import { describe, expect, it } from 'vitest';
import type { IbkrOrder } from '../ibkr/types';
import { orderSourceCell } from './PositionsOrdersPanel';

const SELL: IbkrOrder = {
  order_id: 68,
  symbol: 'ACN',
  side: 'SELL',
  qty: 100,
  filled_qty: 100,
  remaining_qty: 0,
  order_type: 'MKT',
  limit_price: null,
  outside_rth: true,
  status: 'Filled',
};

describe('the Account page Source cell names who sent it (2026-10-01)', () => {
  it('reads a breaker\'s sell as the breaker, like the Orders table', () => {
    expect(orderSourceCell({ ...SELL, order_source: 'flatten', order_origin: 'bot_trip' }, undefined).label).toBe(
      'Bot trip',
    );
    expect(orderSourceCell({ ...SELL, order_source: 'bot', order_origin: 'auto_entry' }, undefined)).toEqual({
      label: 'Auto-entry',
      bot: true,
    });
  });

  it('keeps its own label when no origin was recorded', () => {
    expect(orderSourceCell({ ...SELL, order_source: 'flatten' }, undefined).label).toBe('Flatten');
  });
});
