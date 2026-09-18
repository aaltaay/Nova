import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  appendTapePrint,
  emptyTapeState,
  flushPendingTapePrints,
  tapeMessageAllowed,
  tapeSymbolKey,
  type TapePrint,
} from './tapeFeed';

const here = dirname(fileURLToPath(import.meta.url));

function makePrint(symbol: string, price = 1): TapePrint {
  return {
    symbol,
    time: '2026-07-15T14:00:00Z',
    price,
    size: 100,
    exchange: 'ISLAND',
    side: 'ask',
  };
}

describe('tapeSymbolKey', () => {
  it('uppercases symbols and maps null/empty to null', () => {
    expect(tapeSymbolKey('aapl')).toBe('AAPL');
    expect(tapeSymbolKey(null)).toBeNull();
  });
});

describe('emptyTapeState', () => {
  it('clears prints and connection flags (symbol-change reset)', () => {
    expect(emptyTapeState()).toEqual({
      prints: [],
      connected: false,
      error: null,
    });
  });
});

describe('tapeMessageAllowed', () => {
  it('accepts matching symbols case-insensitively', () => {
    expect(tapeMessageAllowed('aapl', 'AAPL')).toBe(true);
    expect(tapeMessageAllowed('AAPL', 'AAPL')).toBe(true);
  });

  it('rejects stale prints from a different symbol', () => {
    expect(tapeMessageAllowed('MSFT', 'AAPL')).toBe(false);
    expect(tapeMessageAllowed('nxTc', 'MVO')).toBe(false);
  });

  it('allows messages without a string symbol', () => {
    expect(tapeMessageAllowed(undefined, 'AAPL')).toBe(true);
    expect(tapeMessageAllowed(null, 'AAPL')).toBe(true);
  });
});

describe('appendTapePrint', () => {
  it('prepends newest first and caps row count', () => {
    const a = makePrint('AAPL', 1);
    const b = makePrint('AAPL', 2);
    const c = makePrint('AAPL', 3);
    const next = appendTapePrint(appendTapePrint([a], b, 2), c, 2);
    expect(next).toHaveLength(2);
    expect(next[0].price).toBe(3);
    expect(next[1].price).toBe(2);
  });
});

describe('flushPendingTapePrints', () => {
  it('keeps arrival order (newest first) and does not invent prints', () => {
    const a = { ...makePrint('AAPL', 1), time: '2026-09-18T13:00:00.000Z' };
    const b = { ...makePrint('AAPL', 2), time: '2026-09-18T13:00:00.010Z' };
    const c = { ...makePrint('AAPL', 3), time: '2026-09-18T13:00:00.020Z' };
    const next = flushPendingTapePrints([], [a, b, c]);
    expect(next.map(p => p.price)).toEqual([3, 2, 1]);
    expect(next).toHaveLength(3);
  });

  it('caps the ring without dropping a newer pending print', () => {
    const existing = [makePrint('AAPL', 10), makePrint('AAPL', 9)];
    const pending = [makePrint('AAPL', 11), makePrint('AAPL', 12)];
    const next = flushPendingTapePrints(existing, pending, 3);
    expect(next.map(p => p.price)).toEqual([12, 11, 10]);
  });
});

describe('Time & Sales tape ownership', () => {
  it('TimeSalesPanel owns useIbkrTape; DepthAndTape does not', () => {
    const panel = readFileSync(join(here, 'TimeSalesPanel.tsx'), 'utf8');
    const glue = readFileSync(join(here, 'DepthAndTape.tsx'), 'utf8');
    expect(panel).toMatch(/useIbkrTape\(/);
    expect(glue).not.toMatch(/useIbkrTape/);
    expect(glue).toMatch(/Level2Module/);
    expect(glue).toMatch(/TimeSalesModule/);
  });
});
