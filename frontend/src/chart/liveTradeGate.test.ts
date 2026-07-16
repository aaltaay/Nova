import { describe, expect, it } from 'vitest';
import { tradeMatchesChartSymbol } from './liveTradeGate';

describe('tradeMatchesChartSymbol', () => {
  it('accepts trades without a symbol (legacy callers)', () => {
    expect(tradeMatchesChartSymbol('AAPL', null)).toBe(true);
    expect(tradeMatchesChartSymbol('AAPL', undefined)).toBe(true);
  });

  it('rejects mismatched symbols case-insensitively', () => {
    expect(tradeMatchesChartSymbol('AAPL', 'MSFT')).toBe(false);
    expect(tradeMatchesChartSymbol('aapl', 'AAPL')).toBe(true);
  });
});
