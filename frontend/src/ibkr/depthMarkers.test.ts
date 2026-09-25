/**
 * The plan's ENTRY / STOP / TARGET in the Level 2 book (ADR 037): which column each joins and where it
 * sits among the shown rows -- PFSA at 08:07:02 on 2026-09-24, as the approved mockup drew it.
 */
import { describe, expect, it } from 'vitest';
import { placeMarkers, splitMarkers, type DepthMarker } from './depthMarkers';
import type { DepthLevel } from './types';

const bid = (price: number): DepthLevel => ({ price, size: 100, side: 'bid', mm: 'NSDQ' });
const ask = (price: number): DepthLevel => ({ price, size: 100, side: 'ask', mm: 'NSDQ' });
const bids = [4.21, 4.20, 4.19, 4.18, 4.16, 4.15, 4.10, 4.08, 4.07, 4.05].map(bid);
const asks = [4.25, 4.25, 4.25, 4.30, 4.31, 4.34, 4.37, 4.40, 4.41, 4.42].map(ask);

function marker(id: string, price: number, rests: 'bid' | 'ask'): DepthMarker {
  return { id, price, label: `${id.toUpperCase()} ${price}`, color: '#0a84ff', working: false, rests, tip: '' };
}
const ENTRY = marker('entry', 4.27, 'bid');
const STOP = marker('stop', 4.14, 'bid');
const TARGET = marker('target', 4.52, 'ask');

describe('the plan in the Level 2 book', () => {
  it("puts ENTRY with the asks it would take, STOP among the bids and TARGET past the book's reach", () => {
    const sides = splitMarkers([ENTRY, STOP, TARGET], bids, asks);
    expect(sides.bid.map(m => m.id)).toEqual(['stop']);
    expect(sides.ask.map(m => m.id)).toEqual(['entry', 'target']);
    expect(placeMarkers('ask', asks, sides.ask).map(m => [m.id, m.before, m.beyond])).toEqual([
      ['entry', 3, false], ['target', 10, true],
    ]);
    expect(placeMarkers('bid', bids, sides.bid).map(m => [m.id, m.before, m.beyond])).toEqual([['stop', 6, false]]);
  });

  it('a level at a shown price follows the orders already resting there', () => {
    expect(placeMarkers('ask', asks, [{ ...ENTRY, price: 4.25 }])[0]).toMatchObject({ before: 3, beyond: false });
    expect(placeMarkers('bid', bids, [{ ...STOP, price: 4.15 }])[0]).toMatchObject({ before: 6, beyond: false });
  });

  it('inside the spread a level joins the side it would rest on; an empty book draws none', () => {
    const inside = { ...ENTRY, price: 4.23 };
    expect(splitMarkers([inside], bids, asks).bid).toEqual([inside]);
    expect(placeMarkers('bid', bids, [inside])[0].before).toBe(0);
    expect(splitMarkers([{ ...TARGET, price: 4.23 }], bids, asks).ask.map(m => m.price)).toEqual([4.23]);
    expect(splitMarkers([ENTRY, STOP, TARGET], [], [])).toEqual({ bid: [], ask: [] });
  });
});
