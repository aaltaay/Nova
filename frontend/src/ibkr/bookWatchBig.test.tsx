/**
 * @vitest-environment jsdom
 *
 * Big sellers and buyers on the Level 2 ladder (#984): the watcher's walls folded from the depth socket, drawn as
 * a dark framed block with a tag and a traded bar, and named over the column head -- size, share of the float,
 * seconds of lit volume -- then taken, pulled, pulled as the price came or out of view, fading out.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import { L2_BIG_ROW_BG, L2_BIG_SHOW_ENDED_MS } from '../constants';
import { applyBookWatchFrame, bookWatchBusy, type BookWatchState } from './bookWatch';
import { bigBanner, bigRows, clearWords, floatPct } from './bookWatchBig';
import { MontageSide } from './DepthLadder';
import type { DepthLevel } from './types';

const NOW_S = 1_790_682_311.878;
const NOW_MS = 7_000_000;

function wall(over: Record<string, unknown> = {}) {
  return {
    id: '1790682300000-XYZ-ask-3.45', kind: 'big_seller', side: 'ask', price: 3.45, state: 'holding',
    size_first: 48_200, size_now: 48_200, size_peak: 48_200, traded: 0, median_level: 2_400, multiple: 20.1,
    first_seen_ts: NOW_S - 20, seen_from_start: false, called_ts: NOW_S - 17, ended_ts: null, held_sec: 20,
    distance: 0.01, distance_pct: 0.29, distance_called: 0.01, on_approach: null, back: null, clear_sec: 40.2,
    how: null, left: null, ...over,
  };
}

function frame(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1, now: NOW_S, reset: true, seq: 0, watching: true, reason: null, window_sec: 60,
    sides: {
      bid: { pulled_shares: 0, filled_shares: 0, large_pulls: 0, hidden_shares: 0 },
      ask: { pulled_shares: 0, filled_shares: 0, large_pulls: 0, hidden_shares: 0 },
    },
    drops: [], hidden: [], big: [wall()], big_float: { shares: 2_500_000, contradicted: false },
    ...over,
  };
}

function state(over: Record<string, unknown> = {}, nowMs = NOW_MS): BookWatchState {
  const s = applyBookWatchFrame(null, frame(over), nowMs);
  if (!s) throw new Error('no state');
  return s;
}

const lvl = (price: number, size: number, side: 'bid' | 'ask', mm = 'NSDQ'): DepthLevel => ({ price, size, side, mm });
const ASKS = [lvl(3.44, 1800, 'ask'), lvl(3.45, 30_000, 'ask'), lvl(3.45, 18_200, 'ask', 'ARCA'), lvl(3.46, 2100, 'ask')];
const text = (s: BookWatchState, side: 'bid' | 'ask' = 'ask', nowMs = NOW_MS) =>
  bigBanner(s, side, nowMs)?.parts.map(p => p.sep + p.text).join('');

describe('folding the walls', () => {
  it('reads each wall and the float, on this page clock', () => {
    const s = state();
    expect(s.big).toHaveLength(1);
    expect(s.big[0]).toMatchObject({ side: 'ask', price: 3.45, state: 'holding', sizeNow: 48_200, clearSec: 40.2 });
    expect(s.big[0].firstSeenMs).toBeCloseTo(NOW_MS - 20_000, 3);
    expect(s.bigFloat).toEqual({ shares: 2_500_000, contradicted: false });
  });

  it('keeps the list through a frame that says nothing of it, and replaces it with one that does', () => {
    const s = state();
    const { big: _b, big_float: _f, ...quiet } = frame({ reset: false });
    expect(applyBookWatchFrame(s, quiet, NOW_MS)?.big).toHaveLength(1);
    expect(applyBookWatchFrame(s, frame({ reset: false, big: [] }), NOW_MS)?.big).toEqual([]);
  });

  it('reads a backend without walls as none, and drops a wall it cannot read', () => {
    const { big: _b, big_float: _f, ...old } = frame();
    expect(applyBookWatchFrame(null, old, NOW_MS)).toMatchObject({ big: [], bigFloat: null });
    expect(state({ big: [wall({ state: 'mystery' }), { price: 'x' }] }).big).toEqual([]);
  });
});

describe('the block', () => {
  it('frames every row at the price, tags the first and bars the last once something traded', () => {
    const rows = bigRows(state({ big: [wall({ traded: 18_400, size_now: 29_800 })] }), 'ask', ASKS, NOW_MS);
    expect([...rows.keys()]).toEqual([1, 2]);
    expect(rows.get(1)).toMatchObject({ first: true, last: false, tag: 'Big seller', takenPct: null });
    expect(rows.get(2)).toMatchObject({ first: false, last: true, tag: null, takenPct: 38 });
    expect(rows.get(1)?.tip).toContain('18,400 traded at 3.45 since.');
  });

  it('draws nothing for a wall that left or ended, or on the other side', () => {
    expect(bigRows(state({ big: [wall({ state: 'left' })] }), 'ask', ASKS, NOW_MS).size).toBe(0);
    expect(bigRows(state({ big: [wall({ state: 'pulled', ended_ts: NOW_S })] }), 'ask', ASKS, NOW_MS).size).toBe(0);
    expect(bigRows(state(), 'bid', ASKS, NOW_MS).size).toBe(0);
  });
});

describe('the banner', () => {
  it('names the wall with its size, share of the float and seconds of lit volume', () => {
    expect(text(state())).toBe('Big seller 3.45 · 48.2K · 1.9% of float · 40 s of lit volume');
    expect(bigBanner(state(), 'ask', NOW_MS)?.kind).toBe('holding');
  });

  it('counts down what is left as it trades, and says when it came back', () => {
    const hit = state({ big: [wall({ traded: 18_400, size_now: 29_800, clear_sec: 24.8 })] });
    expect(text(hit)).toBe('Big seller 3.45 · 29.8K left · 18.4K taken · 1.2% of float · 25 s of lit volume');
    const back = state({ big: [wall({ back: { pulled: 1, last_ended_ts: NOW_S - 90, last_size: 41_000 } })] });
    expect(text(back)).toContain('back · 2nd in 5 min');
    expect(bigBanner(back, 'ask', NOW_MS)?.tip).toContain('Not necessarily the same seller.');
  });

  it('marks a float that may be out of date, and leaves out what is unknown', () => {
    expect(text(state({ big_float: { shares: 2_500_000, contradicted: true } }))).toContain('1.9% of float?');
    expect(text(state({ big_float: null, big: [wall({ clear_sec: null })] }))).toBe('Big seller 3.45 · 48.2K');
    expect(bigBanner(state({ big_float: null }), 'ask', NOW_MS)?.tip).toContain('No float is known for this stock yet.');
  });

  it('says how it ended: taken, pulled, pulled as the price came, out of view', () => {
    const end = (over: Record<string, unknown>) => state({ big: [wall({ ended_ts: NOW_S - 1, ...over })] });
    const left = { before: 48_200, after: 0, filled: 7_200 };
    expect(text(end({ state: 'eaten', traded: 47_000 }))).toBe('✓ Big seller 3.45 taken · 47.0K traded');
    expect(text(end({ state: 'pulled', on_approach: false, left }))).toBe('✕ Big seller 3.45 pulled · 41.0K untraded');
    expect(text(end({ state: 'pulled', on_approach: true, left }))).toBe('✕ Big seller 3.45 pulled as price came · 41.0K untraded');
    expect(text(end({ state: 'lost' }))).toBe('Big seller 3.45 out of view · unknown');
    expect(bigBanner(end({ state: 'pulled', on_approach: true, left }), 'ask', NOW_MS)?.kind).toBe('approach');
    expect(bigBanner(end({ state: 'lost' }), 'ask', NOW_MS)?.tip).toContain('never called pulled');
  });

  it('prefers one that holds over one that ended, and fades the ended one out', () => {
    const both = state({ big: [wall({ id: 'a', price: 3.47, state: 'pulled', ended_ts: NOW_S - 1 }), wall()] });
    expect(bigBanner(both, 'ask', NOW_MS)?.kind).toBe('holding');
    const ended = state({ big: [wall({ state: 'eaten', ended_ts: NOW_S })] });
    expect(bigBanner(ended, 'ask', NOW_MS)?.opacity).toBe(1);
    expect(bigBanner(ended, 'ask', NOW_MS + L2_BIG_SHOW_ENDED_MS - 5_000)?.opacity).toBeCloseTo(0.5, 5);
    expect(bigBanner(ended, 'ask', NOW_MS + L2_BIG_SHOW_ENDED_MS)).toBeNull();
    expect(bookWatchBusy(ended, NOW_MS + 1_000)).toBe(true);
  });

  it('mirrors on the bid and says nothing without a watched line', () => {
    const buyer = state({ big: [wall({ id: 'b', side: 'bid', kind: 'big_buyer', price: 3.42 })] });
    expect(text(buyer, 'bid')).toMatch(/^Big buyer 3\.42 · 48\.2K/);
    expect(bigBanner(buyer, 'ask', NOW_MS)).toBeNull();
    expect(bigBanner(state({ watching: false }), 'ask', NOW_MS)).toBeNull();
  });
});

describe('words', () => {
  it('writes seconds and float shares plainly', () => {
    expect([clearWords(0.2), clearWords(40.4), clearWords(270), clearWords(1500), clearWords(7300)])
      .toEqual(['1 s', '40 s', '4.5 min', '25 min', '2 h+']);
    expect([floatPct(48_200, { shares: 2_500_000, contradicted: false }), floatPct(400_000, { shares: 2_500_000, contradicted: false }),
      floatPct(100, { shares: 2_500_000, contradicted: false })]).toEqual(['1.9%', '16%', '<0.1%']);
  });
});

describe('on the ladder', () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
  });

  it('turns the rows into the block and puts the banner over the column head', () => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    const watch = state({ big: [wall({ traded: 18_400, size_now: 29_800 })] });
    act(() => root?.render(<MontageSide side="ask" levels={ASKS} peak={30_000} watch={watch} nowMs={NOW_MS} />));
    const rows = container.querySelectorAll<HTMLElement>('.das-l2-row');
    expect(rows[1].className).toContain('das-l2-row--big das-l2-row--big-first');
    expect(rows[2].className).toContain('das-l2-row--big-last');
    expect(rows[1].style.backgroundColor).toBe('rgb(11, 11, 11)');
    expect(L2_BIG_ROW_BG).toBe('#0b0b0b');
    expect(rows[0].className).not.toContain('das-l2-row--big');
    expect(rows[1].querySelector('.das-l2-gauge')).toBeNull();
    expect(container.querySelector('[data-testid="l2-big-tag"]')?.textContent).toBe('Big seller');
    expect(rows[2].querySelector<HTMLElement>('.das-l2-bigbar > span')?.style.width).toBe('38%');
    expect(container.querySelector('[data-testid="l2-big-ask"]')?.textContent)
      .toBe('Big seller 3.45 · 29.8K left · 18.4K taken · 1.2% of float · 40 s of lit volume');
  });
});
