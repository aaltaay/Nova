/**
 * What left the book on the Level 2 ladder (ADR 033 amendment, 2026-09-29): the book watcher's verdicts
 * folded from the depth socket, placed between the rows, tagged on prices pulled in the last minute, and
 * summed per side. The numbers are SSTI's at 07:45:11 on 2026-09-29 (Session Record, the watcher's own
 * detector).
 */
import { describe, expect, it } from 'vitest';
import { L2_PULL_MARK_FADE_MS, L2_PULL_MARK_SHOW_MS } from '../constants';
import { applyBookWatchFrame, bookWatchBusy, pulledHere, pullMarks, pullsLine, type BookWatchState } from './bookWatch';
import type { DepthLevel } from './types';

const NOW_S = 1_790_682_311.878; // 07:45:11 ET
const NOW_MS = 5_000_000; // this page's clock: unrelated to the backend's on purpose

function drop(seq: number, over: Record<string, unknown>) {
  return {
    seq, ts: NOW_S - 1, side: 'ask', price: 8.25, dropped: 2000, pulled: 2000, filled: 0, outcome: 'pulled',
    level_before: 2100, level_after: 100, median_level: 300, distance_ticks: 0, distance_at_post_ticks: 5,
    lifetime_sec: 0.653, approached: true, large_pull: true, on_approach: true, ...over,
  };
}

function frame(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1, now: NOW_S, reset: true, seq: 3, watching: true, reason: null, window_sec: 60,
    sides: {
      bid: { pulled_shares: 15424, filled_shares: 1849, large_pulls: 3 },
      ask: { pulled_shares: 7571, filled_shares: 9482, large_pulls: 1 },
    },
    drops: [
      drop(1, { ts: NOW_S - 1.5, price: 8.19, dropped: 3000, pulled: 0, filled: 3000, outcome: 'traded', large_pull: false, on_approach: false, lifetime_sec: 8.223 }),
      drop(2, { ts: NOW_S - 0.95, price: 8.2, dropped: 5200, pulled: 0, filled: 5200, outcome: 'traded', large_pull: false, on_approach: false, lifetime_sec: 1.051 }),
      drop(3, { ts: NOW_S - 0.8 }),
      drop(4, { ts: NOW_S - 25, side: 'bid', price: 8.05, pulled: 5800, dropped: 5800, level_before: 5800, level_after: 0, on_approach: false }),
      drop(5, { ts: NOW_S - 15, side: 'bid', price: 8.05, pulled: 5800, dropped: 5800, level_before: 5800, level_after: 0, on_approach: false }),
    ],
    note: 'Hints consistent with spoofing -- never a detection.',
    ...over,
  };
}

const lvl = (price: number, size: number, side: 'bid' | 'ask'): DepthLevel => ({ price, size, side, mm: 'NSDQ' });
const ASKS = [lvl(8.25, 100, 'ask'), lvl(8.25, 2000, 'ask'), lvl(8.26, 2000, 'ask'), lvl(8.28, 2000, 'ask')];
const BIDS = [lvl(8.15, 189, 'bid'), lvl(8.08, 1000, 'bid'), lvl(8.05, 5800, 'bid'), lvl(8.04, 500, 'bid')];

function state(over: Record<string, unknown> = {}): BookWatchState {
  const s = applyBookWatchFrame(null, frame(over), NOW_MS);
  if (!s) throw new Error('no state');
  return s;
}

describe('folding the frames', () => {
  it('moves each drop onto this page clock through the frame now', () => {
    const s = state();
    expect(s.drops.find(d => d.seq === 3)?.atMs).toBeCloseTo(NOW_MS - 800, 3);
    expect(s.sides?.bid).toEqual({ pulled: 15424, traded: 1849, largePulls: 3, hidden: 0 }); // no hidden_shares: 0
  });

  it('adds only verdicts it has not seen, and a reset starts over', () => {
    const first = state();
    const next = applyBookWatchFrame(first, frame({ reset: false, drops: [drop(3, {}), drop(6, { price: 8.26 })] }), NOW_MS);
    expect(next?.drops.map(d => d.seq)).toEqual([1, 2, 3, 4, 5, 6]);
    const reset = applyBookWatchFrame(next, frame({ drops: [drop(9, {})] }), NOW_MS);
    expect(reset?.drops.map(d => d.seq)).toEqual([9]);
  });

  it('ignores a frame of another schema instead of guessing', () => {
    const first = state();
    expect(applyBookWatchFrame(first, frame({ schema_version: 2, drops: [] }), NOW_MS)).toBe(first);
  });

  it('forgets a drop older than the minute', () => {
    const s = state({ drops: [drop(1, { ts: NOW_S - 61 })] });
    expect(s.drops).toEqual([]);
    expect(bookWatchBusy(state(), NOW_MS)).toBe(true);
    expect(bookWatchBusy(state(), NOW_MS + 61_000)).toBe(false);
  });
});

describe('marks between the rows', () => {
  it('shares one traded mark for a sweep and marks the pull where the size was', () => {
    const marks = pullMarks(state(), 'ask', ASKS, NOW_MS);
    const traded = marks.find(m => m.kind === 'traded');
    const pulled = marks.find(m => m.kind === 'approach');
    expect(traded).toMatchObject({ before: 0, label: '✓ 8,200 traded', title: '8,200 offered traded' });
    expect(traded?.tip).toContain('3,000 at 8.19');
    expect(traded?.tip).toContain('5,200 at 8.20');
    expect(pulled).toMatchObject({ before: 2, label: '✕ 2,000 pulled', title: '2,000 offered at 8.25 pulled' });
    expect(pulled?.tip).toContain('pulled as the price came 5 ticks closer, after resting 0.65 s');
    expect(pulled?.tip).toContain('2,100 was there; 100 stayed.');
    expect(pulled?.tip).toContain('never a detection');
  });

  it('writes both verdicts short when they share a place', () => {
    const s = state({ drops: [
      drop(1, { price: 8.19, pulled: 0, filled: 3000, outcome: 'traded', large_pull: false, on_approach: false }),
      drop(2, { price: 8.21, on_approach: false }),
    ] });
    expect(pullMarks(s, 'ask', ASKS, NOW_MS).map(m => m.label)).toEqual(['✕ 2,000', '✓ 3,000']);
  });

  it('fades over the last seconds and then goes', () => {
    const s = state();
    const age = (ms: number) => pullMarks(s, 'ask', ASKS, NOW_MS + ms).find(m => m.kind === 'approach');
    expect(age(0)?.opacity).toBe(1);
    expect(age(L2_PULL_MARK_SHOW_MS - 800 - L2_PULL_MARK_FADE_MS / 2)?.opacity).toBeCloseTo(0.5, 1);
    expect(age(L2_PULL_MARK_SHOW_MS)).toBeUndefined();
  });

  it('puts a price deeper than the rows after the last one, pointing down', () => {
    const s = state({ drops: [drop(1, { price: 8.9, on_approach: false })] });
    expect(pullMarks(s, 'ask', ASKS, NOW_MS)[0]).toMatchObject({ before: ASKS.length, beyond: true, label: '✕ 2,000 pulled ↓' });
  });
});

describe('prices pulled in the last minute', () => {
  it('counts the large pulls at a shown price and says what sits there now', () => {
    const here = pulledHere(state(), 'bid', BIDS, NOW_MS);
    const at805 = here.get('8.0500');
    expect(at805?.count).toBe(2);
    expect(at805?.title).toBe('8.05: pulled here twice in the last minute');
    expect(at805?.tip).toContain('5,800 bid pulled 25.0 s ago, none traded');
    expect(at805?.tip).toContain('5,800 bid there now.');
    expect(here.has('8.0800')).toBe(false); // nothing large was pulled there in this frame
  });

  it('leaves a price that is no longer shown and a traded level alone', () => {
    expect(pulledHere(state(), 'bid', [lvl(8.15, 189, 'bid')], NOW_MS).size).toBe(0);
    expect(pulledHere(state(), 'ask', ASKS, NOW_MS).has('8.1900')).toBe(false);
  });
});

describe('each side over the last minute', () => {
  it('turns amber only when pulled is well over traded', () => {
    const s = state();
    expect(pullsLine(s, 'bid')).toMatchObject({ watching: true, pulled: '✕ 15.4K', traded: '✓ 1.8K', warn: true, title: 'Bids, last 60 s' });
    expect(pullsLine(s, 'ask')).toMatchObject({ pulled: '✕ 7.6K', traded: '✓ 9.5K', warn: false });
    expect(pullsLine(s, 'bid')?.tip).toContain('15,424 shares left the bids without trading; 1,849 traded there.');
  });

  it('says why it has nothing when the ladder shows no live line', () => {
    const s = state({ watching: false, reason: 'Level 2 is replaying a recording here; the book watcher reads only the live line.', sides: null, drops: [] });
    expect(pullsLine(s, 'bid')).toMatchObject({ watching: false });
    expect(pullsLine(s, 'bid')?.tip).toContain('replaying a recording');
    expect(pullMarks(s, 'ask', ASKS, NOW_MS)).toEqual([]);
  });
});
