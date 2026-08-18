import { describe, expect, it } from 'vitest';
import { tickerDetailFromHttp } from './tickerStreamHttp';

describe('tickerDetailFromHttp', () => {
  it('accepts a matching REST ticker body', () => {
    const row = tickerDetailFromHttp(
      { symbol: 'F', snapshot: { latest_trade: { price: 14.05 } } },
      'f',
    );
    expect(row?.symbol).toBe('F');
  });

  it('rejects a different symbol, errors, or missing snapshot', () => {
    expect(tickerDetailFromHttp({ symbol: 'AAPL', snapshot: {} }, 'F')).toBeNull();
    expect(tickerDetailFromHttp({ symbol: 'F', error: 'no keys' }, 'F')).toBeNull();
    expect(tickerDetailFromHttp({ symbol: 'F' }, 'F')).toBeNull();
  });
});
