import { describe, expect, it } from 'vitest';
import { boardListForSymbol, type BoardLists } from './boardListForSymbol';

const lists: BoardLists = {
  gappers: [{ symbol: 'GRML' }, { symbol: 'VXTL' }],
  gainers: [{ symbol: 'grml' }, { symbol: 'BRNQ' }],
  losers: [],
  afterhours: [{ symbol: 'QNME' }],
  large_cap: [{ symbol: 'AAPL' }],
};

describe('boardListForSymbol', () => {
  it('keeps the current list when it already holds the symbol', () => {
    expect(boardListForSymbol('grml', 'gainers', lists)).toBe('gainers');
    expect(boardListForSymbol('GRML', 'gappers', lists)).toBe('gappers');
  });

  it('switches to the first scanner list that holds the symbol', () => {
    expect(boardListForSymbol('BRNQ', 'gappers', lists)).toBe('gainers');
    expect(boardListForSymbol('QNME', 'gappers', lists)).toBe('afterhours');
    expect(boardListForSymbol('AAPL', 'catalysts', lists)).toBe('large_cap');
  });

  it('answers null when no list holds it -- the board stays, nothing is invented', () => {
    expect(boardListForSymbol('ZZZZ', 'gappers', lists)).toBeNull();
    expect(boardListForSymbol('  ', 'gappers', lists)).toBeNull();
  });
});
