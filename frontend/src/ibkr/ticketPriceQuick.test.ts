import { describe, expect, it } from 'vitest';
import { quickPriceFromBook } from './ticketPriceQuick';

const BOOK = { symbol: 'GRML', bid: 8.89, ask: 8.91 };

describe('quickPriceFromBook', () => {
  it('reads bid, ask and the cent-rounded mid from the live book', () => {
    expect(quickPriceFromBook('bid', BOOK, 'grml')).toBe('8.89');
    expect(quickPriceFromBook('ask', BOOK, 'GRML')).toBe('8.91');
    expect(quickPriceFromBook('mid', BOOK, 'GRML')).toBe('8.90');
    expect(quickPriceFromBook('mid', { symbol: 'X', bid: 1.01, ask: 1.02 }, 'X')).toBe('1.02');
  });

  it('never substitutes another symbol, a one-sided book or no book at all', () => {
    expect(quickPriceFromBook('bid', BOOK, 'QNME')).toBeNull();
    expect(quickPriceFromBook('ask', { ...BOOK, ask: null }, 'GRML')).toBeNull();
    expect(quickPriceFromBook('mid', { ...BOOK, bid: 0 }, 'GRML')).toBeNull();
    expect(quickPriceFromBook('mid', null, 'GRML')).toBeNull();
  });
});
