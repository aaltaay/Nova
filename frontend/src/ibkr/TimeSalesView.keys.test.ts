import { describe, expect, it } from 'vitest';
import type { TapePrint } from './tapeFeed';
import { tapeRowKey } from './TapeRow';

const print = (over: Partial<TapePrint> = {}): TapePrint => ({
  symbol: 'AMOD', time: '2026-10-02T13:30:00.000Z', price: 2.5, size: 100, exchange: 'NSDQ', ...over,
});

describe('tapeRowKey', () => {
  it('keeps a live print on one row as newer prints arrive above it', () => {
    const p = print();
    const first = tapeRowKey(p);
    // A newer print lands first; the older row must keep its key, or React rebuilds every row.
    tapeRowKey(print({ price: 2.51 }));
    expect(tapeRowKey(p)).toBe(first);
  });

  it('tells apart two prints with the same time, price and size', () => {
    expect(tapeRowKey(print())).not.toBe(tapeRowKey(print()));
  });

  it('uses the replay identity when the print has one', () => {
    expect(tapeRowKey(print({ replayId: 'job:42' }))).toBe('job:42');
  });
});
