import { describe, expect, it } from 'vitest';
import {
  STOCK_VIEW_QUERY_VIEW,
  buildStockViewUrl,
  parseStockViewSymbol,
} from './stockViewNav';

describe('stockViewNav', () => {
  it('builds a Stock View URL with view=stock and uppercased symbol', () => {
    const url = buildStockViewUrl('lvlu', 'http://127.0.0.1:5173/');
    expect(url).toContain('view=stock');
    expect(url).toContain('symbol=LVLU');
  });

  it('parses the symbol only when view=stock', () => {
    expect(parseStockViewSymbol('?view=stock&symbol=lvlu')).toBe('LVLU');
    expect(parseStockViewSymbol('?symbol=LVLU')).toBeNull();
    expect(parseStockViewSymbol(`?view=${STOCK_VIEW_QUERY_VIEW}`)).toBeNull();
  });
});
