/**
 * Level 2 marks a short plan's SHORT and STOP ↑ with the asks and its TARGET ↓ with the bids, and a held short's
 * STOP ↑ and NEXT ↓ the same way (ADR 048).
 */
import { describe, expect, it } from 'vitest';
import { heldMarkers } from './heldView';
import { normalizeHeld } from './heldRead';
import { level2Markers } from './whoTradesModel';

const LEVELS = {
  entry: { price: 5.77, behind: 'plan' as const },
  stop: { price: 5.89, behind: 'plan' as const },
  target: { price: 5.53, behind: 'plan' as const },
};

describe('short markers on Level 2', () => {
  it('a short plan: SHORT and STOP ↑ with the asks, TARGET ↓ with the bids', () => {
    const marks = level2Markers(LEVELS, 'short');
    expect(marks.map(m => [m.label, m.rests])).toEqual([
      ['SHORT 5.77', 'ask'], ['STOP ↑ 5.89', 'ask'], ['TARGET ↓ 5.53', 'bid'],
    ]);
    expect(marks[0].tip).toMatch(/short entry/);
  });

  it('a long plan reads as it always has', () => {
    expect(level2Markers(LEVELS).map(m => [m.label, m.rests])).toEqual([
      ['ENTRY 5.77', 'bid'], ['STOP 5.89', 'bid'], ['TARGET 5.53', 'ask'],
    ]);
  });

  it('a held short: STOP ↑ with the asks, NEXT ↓ with the bids', () => {
    const held = normalizeHeld({
      side: 'short', qty: 416, avg: 5.77, price: 5.47,
      stop: { price: 5.89, source: 'yours', rule: 'your buy stop', printed: false },
      lower: { to: 5.55, round: 5.5, at: 1790000000, text: 'Lower stop to 5.55, 5c over $5.50' },
      ladder: [
        { role: 'stop', price: 5.89, text: 'your buy stop', r: -1, usd: -49.92 },
        { role: 'now', price: 5.47, text: '+124.80 open', r: 2.5, usd: 124.8 },
        { role: 'next', price: 5.35, text: 'bottom ×2', r: 3.5, usd: 174.72 },
      ],
      levels: { room: null },
    });
    expect(held?.side).toBe('short');
    expect(held?.lower?.to).toBe(5.55);
    expect(heldMarkers(held).map(m => [m.label, m.rests])).toEqual([['STOP ↑ 5.89', 'ask'], ['NEXT ↓ 5.35', 'bid']]);
  });
});
