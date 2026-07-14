import { describe, expect, it } from 'vitest';
import {
  bookIsEmpty,
  isOvernightOnlyBook,
  isRenderableBook,
  shouldKeepPriorBook,
} from './depthBookGuards';
import type { DepthBook } from './types';

function book(
  bids: DepthBook['bids'],
  asks: DepthBook['asks'] = [],
  l1 = false,
): DepthBook {
  return { bids, asks, l1_fallback: l1 };
}

const overnightThin: DepthBook = book(
  [{ price: 4.78, size: 100, side: 'bid', mm: 'OVERNIGHT' }],
  [{ price: 4.83, size: 200, side: 'ask', mm: 'OVERNIGHT' }],
);

describe('bookIsEmpty', () => {
  it('is true only when both sides are empty', () => {
    expect(bookIsEmpty(book([], []))).toBe(true);
    expect(bookIsEmpty(overnightThin)).toBe(false);
    expect(bookIsEmpty(book([{ price: 1, size: 1, side: 'bid' }], []))).toBe(false);
  });
});

describe('shouldKeepPriorBook', () => {
  it('keeps a prior overnight/thin book across a transient empty DOM frame', () => {
    const empty = book([], [], false);
    expect(shouldKeepPriorBook(empty, overnightThin)).toBe(true);
  });

  it('does not keep prior when incoming is a real (possibly thin) book', () => {
    expect(shouldKeepPriorBook(overnightThin, overnightThin)).toBe(false);
  });

  it('does not keep prior when incoming is empty L1 fallback', () => {
    expect(shouldKeepPriorBook(book([], [], true), overnightThin)).toBe(false);
  });

  it('does not keep prior when there is nothing to keep', () => {
    expect(shouldKeepPriorBook(book([], []), null)).toBe(false);
  });

  it('never keeps a prior book from a different symbol', () => {
    const prior = { ...overnightThin, symbol: 'NXTC' };
    const empty = { ...book([], [], false), symbol: 'MVO' };
    expect(shouldKeepPriorBook(empty, prior)).toBe(false);
  });
});

describe('isRenderableBook', () => {
  it('treats thin OVERNIGHT after-hours books as renderable', () => {
    expect(isRenderableBook(overnightThin)).toBe(true);
  });

  it('treats L1 fallback as renderable even before first quote', () => {
    expect(isRenderableBook(book([], [], true))).toBe(true);
  });

  it('rejects null and empty non-L1 placeholders', () => {
    expect(isRenderableBook(null)).toBe(false);
    expect(isRenderableBook(book([], [], false))).toBe(false);
  });
});

describe('isOvernightOnlyBook', () => {
  it('is true when every visible MM is OVERNIGHT', () => {
    expect(isOvernightOnlyBook(overnightThin)).toBe(true);
  });

  it('is false when any row is a regular venue (ISLAND/ARCA/…)', () => {
    const mixed = book(
      [{ price: 4.78, size: 100, side: 'bid', mm: 'OVERNIGHT' }],
      [{ price: 4.83, size: 200, side: 'ask', mm: 'ISLAND' }],
    );
    expect(isOvernightOnlyBook(mixed)).toBe(false);
  });
});
