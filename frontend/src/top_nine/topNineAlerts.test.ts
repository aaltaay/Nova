/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { chimeWorthy, newlyHalted, readTopNineMuted, writeTopNineMuted } from './topNineAlerts';
import type { TopNineSwitch } from './topNineMarks';
import type { TopNineRow } from './topNineSnapshot';

function row(symbol: string, rank: number, halted: boolean | null = false): TopNineRow {
  return { symbol, rank, changePct: 0.5, price: 2, volume: 1_000_000, float: 5_000_000, halted };
}

// 2026-10-27 10:00 ET and the next day 10:00 ET.
const TUE_10 = Date.parse('2026-10-27T14:00:00Z');
const WED_10 = Date.parse('2026-10-28T14:00:00Z');

describe('chimeWorthy', () => {
  const sofx7: TopNineSwitch = {
    at: 1,
    moves: [
      { symbol: 'SOFX', from: 8, to: 7, kind: 'up', at: 1 },
      { symbol: 'AEYE', from: 7, to: 8, kind: 'down', at: 1 },
    ],
    left: [],
  };

  it('chimes for a rise or a new stock', () => {
    expect(chimeWorthy(sofx7, new Set())).toBe(true);
    expect(chimeWorthy({ at: 1, moves: [{ symbol: 'KNSA', from: null, to: 8, kind: 'new', at: 1 }], left: ['CLRO'] }, new Set()))
      .toBe(true);
  });

  it('stays quiet when the only riser is muted: the stock it passed only moved down', () => {
    expect(chimeWorthy(sofx7, new Set(['SOFX']))).toBe(false);
  });

  it('stays quiet when only names left', () => {
    expect(chimeWorthy({ at: 1, moves: [], left: ['CLRO'] }, new Set())).toBe(false);
  });
});

describe('newlyHalted', () => {
  it('names a stock that halted since the last board, never on the first board', () => {
    const rows = [row('AIOK', 1, true), row('NEXR', 2)];
    expect(newlyHalted(null, rows, new Set())).toEqual([]);
    expect(newlyHalted(new Set(), rows, new Set())).toEqual(['AIOK']);
    expect(newlyHalted(new Set(['AIOK']), rows, new Set())).toEqual([]);
  });

  it('skips a muted stock and an unknown halt state', () => {
    expect(newlyHalted(new Set(), [row('AIOK', 1, true)], new Set(['AIOK']))).toEqual([]);
    expect(newlyHalted(new Set(), [row('AIOK', 1, null)], new Set())).toEqual([]);
  });
});

describe('muted stocks', () => {
  beforeEach(() => localStorage.clear());

  it('are kept for the desk day and forgotten the next', () => {
    writeTopNineMuted(new Set(['SOFA', 'MFIC']), TUE_10);
    expect([...readTopNineMuted(TUE_10 + 3_600_000)].sort()).toEqual(['MFIC', 'SOFA']);
    expect(readTopNineMuted(WED_10).size).toBe(0);
  });
});
