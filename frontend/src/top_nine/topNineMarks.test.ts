import { describe, expect, it } from 'vitest';
import { TOP_NINE_LOG_MAX, TOP_NINE_MARK_FULL_MS, TOP_NINE_MARK_SOFT_MS } from './topNineConstants';
import { EMPTY_LIST_MARKS, diffTopNine, markLeft, markPhase, moveText, nextListMarks } from './topNineMarks';
import type { TopNineRow } from './topNineSnapshot';

function rows(...symbols: string[]): TopNineRow[] {
  return symbols.map((symbol, i) => ({
    symbol, rank: i + 1, changePct: 0.1, price: 1, volume: 1, float: 1, halted: false,
  }));
}

// The real Gainers switch of 2026-10-16 at 10:14 ET (recorded board).
const AT_1013 = rows('XLAB', 'WORX', 'ZTG', 'SMX', 'FVNNU', 'SGRX', 'TCRT', 'SITC', 'CORD');
const AT_1014 = rows('XLAB', 'ZTG', 'SMX', 'FVNNU', 'WORX', 'SGRX', 'TCRT', 'SITC', 'CORD');

describe('diffTopNine', () => {
  it('marks nothing on the first board -- there is nothing to compare it with', () => {
    expect(diffTopNine(null, AT_1013, 1)).toBeNull();
  });

  it('marks each stock whose rank changed, up or down, with where it came from', () => {
    const prev = Object.fromEntries(AT_1013.map((r) => [r.symbol, r.rank]));
    const sw = diffTopNine(prev, AT_1014, 5);
    expect(sw?.moves).toEqual([
      { symbol: 'ZTG', from: 3, to: 2, kind: 'up', at: 5 },
      { symbol: 'SMX', from: 4, to: 3, kind: 'up', at: 5 },
      { symbol: 'FVNNU', from: 5, to: 4, kind: 'up', at: 5 },
      { symbol: 'WORX', from: 2, to: 5, kind: 'down', at: 5 },
    ]);
    expect(sw?.left).toEqual([]);
  });

  it('marks a stock new to the top nine and names the one that left', () => {
    const prev = Object.fromEntries(AT_1013.map((r) => [r.symbol, r.rank]));
    const next = rows('XLAB', 'WORX', 'ZTG', 'SMX', 'FVNNU', 'SGRX', 'TCRT', 'SITC', 'BLNE');
    const sw = diffTopNine(prev, next, 9);
    expect(sw?.moves).toEqual([{ symbol: 'BLNE', from: null, to: 9, kind: 'new', at: 9 }]);
    expect(sw?.left).toEqual(['CORD']);
    expect(moveText(sw!.moves[0])).toBe('NEW');
  });

  it('answers null when the board is the same', () => {
    const prev = Object.fromEntries(AT_1013.map((r) => [r.symbol, r.rank]));
    expect(diffTopNine(prev, AT_1013, 2)).toBeNull();
  });
});

describe('mark phases', () => {
  const move = { symbol: 'ZTG', from: 3, to: 2, kind: 'up' as const, at: 1_000 };

  it('is full for 30 s, soft until 2.5 min, then gone', () => {
    expect(markPhase(move, 1_000)).toBe('full');
    expect(markPhase(move, 1_000 + TOP_NINE_MARK_FULL_MS - 1)).toBe('full');
    expect(markPhase(move, 1_000 + TOP_NINE_MARK_FULL_MS)).toBe('soft');
    expect(markPhase(move, 1_000 + TOP_NINE_MARK_SOFT_MS)).toBe('none');
    expect(markPhase(undefined, 1_000)).toBe('none');
  });

  it('runs the timer bar from full to empty', () => {
    expect(markLeft(move, 1_000)).toBe(1);
    expect(markLeft(move, 1_000 + TOP_NINE_MARK_FULL_MS / 2)).toBeCloseTo(0.5);
    expect(markLeft(move, 1_000 + TOP_NINE_MARK_FULL_MS * 2)).toBe(0);
    expect(moveText(move)).toBe('3 → 2');
  });
});

describe('nextListMarks', () => {
  it('keeps marks while they show, logs each switch newest first, and drops expired marks', () => {
    let { state } = nextListMarks(EMPTY_LIST_MARKS, AT_1013, 0);
    expect(state.log).toEqual([]);
    const step = nextListMarks(state, AT_1014, 10);
    state = step.state;
    expect(step.switched?.moves.map((m) => m.symbol)).toEqual(['ZTG', 'SMX', 'FVNNU', 'WORX']);
    expect(Object.keys(state.marks).sort()).toEqual(['FVNNU', 'SMX', 'WORX', 'ZTG']);
    expect(state.log).toHaveLength(1);

    const later = nextListMarks(state, AT_1014, 10 + TOP_NINE_MARK_SOFT_MS);
    expect(later.switched).toBeNull();
    expect(later.state.marks).toEqual({});
    expect(later.state.log).toHaveLength(1);
  });

  it('keeps the board minute a switch happened on', () => {
    const first = nextListMarks(EMPTY_LIST_MARKS, AT_1013, 0, { asOf: 1_792_159_980, replay: true }).state;
    const step = nextListMarks(first, AT_1014, 10, { asOf: 1_792_160_040, replay: true });
    expect(step.switched?.board).toEqual({ asOf: 1_792_160_040, replay: true });
  });

  it('caps the log', () => {
    let state = nextListMarks(EMPTY_LIST_MARKS, AT_1013, 0).state;
    for (let i = 1; i <= TOP_NINE_LOG_MAX + 5; i += 1) {
      state = nextListMarks(state, i % 2 ? AT_1014 : AT_1013, i).state;
    }
    expect(state.log).toHaveLength(TOP_NINE_LOG_MAX);
    expect(state.log[0].at).toBe(TOP_NINE_LOG_MAX + 5);
  });

  it('drops a mark when the stock leaves the top nine', () => {
    let state = nextListMarks(EMPTY_LIST_MARKS, AT_1013, 0).state;
    state = nextListMarks(state, AT_1014, 1).state;
    const without = rows('XLAB', 'ZTG', 'SMX', 'FVNNU', 'SGRX', 'TCRT', 'SITC', 'CORD', 'BLNE');
    state = nextListMarks(state, without, 2).state;
    expect(state.marks.WORX).toBeUndefined();
    expect(state.log[0].left).toEqual(['WORX']);
  });
});
