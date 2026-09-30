/**
 * Hidden sellers and buyers on the Level 2 ladder (ADR 033 amendment, 2026-09-30): the book watcher's words
 * folded from the depth socket, drawn as a violet mark under their price and an outlined row while they hold.
 */
import { describe, expect, it } from 'vitest';
import { L2_HIDDEN_STALE_MS, L2_PULL_MARK_FADE_MS, L2_PULL_MARK_SHOW_MS } from '../constants';
import { applyBookWatchFrame, bookWatchBusy, pullsLine, type BookWatchState } from './bookWatch';
import { hiddenHere, hiddenMarks } from './bookWatchHidden';
import type { DepthLevel } from './types';

const NOW_S = 1_790_682_311.878;
const NOW_MS = 7_000_000;

function word(seq: number, over: Record<string, unknown> = {}) {
  return {
    seq, id: '1790682300000-XYZ-ask-5', event: 'hidden', kind: 'hidden_seller', ts: NOW_S - 0.5, side: 'ask', price: 5,
    state: 'holding', hidden: 12_400, printed: 14_400, shown_max: 2000, shown_now: 1200, prints: 61, refills: 7,
    started_ts: NOW_S - 9.5, last_print_ts: NOW_S - 0.5, flagged_ts: NOW_S - 3, ended_ts: null, ...over,
  };
}

function frame(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1, now: NOW_S, reset: true, seq: 0, hidden_seq: 2, watching: true, reason: null, window_sec: 60,
    sides: {
      bid: { pulled_shares: 4000, filled_shares: 3200, large_pulls: 1, hidden_shares: 0 },
      ask: { pulled_shares: 1100, filled_shares: 2000, large_pulls: 0, hidden_shares: 12_400 },
    },
    drops: [],
    hidden: [word(1, { hidden: 10_000, printed: 12_000 }), word(2)],
    ...over,
  };
}

function state(over: Record<string, unknown> = {}): BookWatchState {
  const s = applyBookWatchFrame(null, frame(over), NOW_MS);
  if (!s) throw new Error('no state');
  return s;
}

const lvl = (price: number, size: number, side: 'bid' | 'ask'): DepthLevel => ({ price, size, side, mm: 'NSDQ' });
const ASKS = [lvl(5, 1200, 'ask'), lvl(5.01, 1500, 'ask'), lvl(5.02, 4500, 'ask')];

describe('folding the hidden words', () => {
  it('keeps one entry per stretch, its newest word', () => {
    const s = state();
    expect(s.hidden).toHaveLength(1);
    expect(s.hidden[0]).toMatchObject({ seq: 2, hidden: 12_400, shownMax: 2000, refills: 7 });
    expect(s.hidden[0].heldSec).toBeCloseTo(9, 3);
    expect(s.hidden[0].atMs).toBeCloseTo(NOW_MS - 500, 3);
    const later = applyBookWatchFrame(s, frame({ reset: false, hidden: [word(3, { state: 'broke', ended_ts: NOW_S })] }), NOW_MS);
    expect(later?.hidden.map(h => h.state)).toEqual(['broke']);
    expect(applyBookWatchFrame(s, frame({ reset: true, hidden: [] }), NOW_MS)?.hidden).toEqual([]);
  });

  it('reads a frame from a backend without hidden words as none', () => {
    const { hidden: _h, ...old } = frame();
    const s = applyBookWatchFrame(null, { ...old, sides: { bid: { pulled_shares: 1, filled_shares: 1, large_pulls: 0 }, ask: { pulled_shares: 1, filled_shares: 1, large_pulls: 0 } } }, NOW_MS);
    expect(s?.hidden).toEqual([]);
    expect(s?.sides?.ask.hidden).toBe(0);
  });

  it('keeps the ladder redrawing while a hidden seller is up', () => {
    expect(bookWatchBusy(state(), NOW_MS)).toBe(true);
    expect(bookWatchBusy(state(), NOW_MS + L2_HIDDEN_STALE_MS + 1000)).toBe(false);
  });
});

describe('the marks', () => {
  it('marks a hidden seller under its price, whole and explained', () => {
    const [mark] = hiddenMarks(state(), 'ask', ASKS, NOW_MS);
    expect(mark).toMatchObject({ kind: 'hidden', before: 1, beyond: false, opacity: 1, label: '◆ 12.4K hidden' });
    expect(mark.title).toBe('Hidden seller at 5.00: 12,400 beyond what it showed');
    expect(mark.tip).toContain('14,400 traded at 5.00 over 9 s; the book never showed more than 2,000 there.');
    expect(mark.tip).toContain('It still holds: nothing has traded through 5.00.');
    expect(mark.tip).toContain('came back 7 times');
    expect(mark.tip).toContain('37% of the time');
    expect(mark.tip).toContain('never a detection');
    expect(hiddenMarks(state(), 'bid', ASKS, NOW_MS)).toEqual([]);
  });

  it('says how it ended, then fades like a pull mark', () => {
    const ended = state({ hidden: [word(2, { state: 'broke', ts: NOW_S, ended_ts: NOW_S })] });
    expect(hiddenMarks(ended, 'ask', ASKS, NOW_MS)[0].label).toBe('◆ 12.4K · broke');
    expect(hiddenMarks(ended, 'ask', ASKS, NOW_MS)[0].tip).toContain('Then a print went through 5.00.');
    const fading = hiddenMarks(ended, 'ask', ASKS, NOW_MS + L2_PULL_MARK_SHOW_MS - L2_PULL_MARK_FADE_MS / 2)[0];
    expect(fading.opacity).toBeGreaterThan(0);
    expect(fading.opacity).toBeLessThan(1);
    expect(hiddenMarks(ended, 'ask', ASKS, NOW_MS + L2_PULL_MARK_SHOW_MS)).toEqual([]);
    const held = state({ hidden: [word(2, { state: 'faded', ts: NOW_S })] });
    expect(hiddenMarks(held, 'ask', ASKS, NOW_MS)[0].label).toBe('◆ 12.4K · held');
  });

  it('draws nothing once the book showed as much, or once the watcher went quiet on it', () => {
    expect(hiddenMarks(state({ hidden: [word(2, { hidden: 0 })] }), 'ask', ASKS, NOW_MS)).toEqual([]);
    expect(hiddenMarks(state(), 'ask', ASKS, NOW_MS + L2_HIDDEN_STALE_MS + 1)).toEqual([]);
  });

  it('outlines the rows it holds at, and only while it holds', () => {
    const here = hiddenHere(state(), 'ask', ASKS, NOW_MS);
    expect([...here.keys()]).toEqual(['5.0000']);
    expect(here.get('5.0000')?.title).toContain('Hidden seller at 5.00');
    expect(hiddenHere(state({ hidden: [word(2, { state: 'broke' })] }), 'ask', ASKS, NOW_MS).size).toBe(0);
    expect(hiddenHere(state(), 'ask', [lvl(5.01, 1500, 'ask')], NOW_MS).size).toBe(0);
  });

  it('names a hidden buyer on the bid side', () => {
    const bid = state({ hidden: [word(2, { side: 'bid', kind: 'hidden_buyer', price: 4.95 })] });
    const [mark] = hiddenMarks(bid, 'bid', [lvl(4.95, 300, 'bid'), lvl(4.94, 800, 'bid')], NOW_MS);
    expect(mark.title).toBe('Hidden buyer at 4.95: 12,400 beyond what it showed');
    expect(mark.tip).toContain('no such difference');
  });
});

describe("each side's line", () => {
  it('adds the hidden size at flagged prices, and says what it is', () => {
    const line = pullsLine(state(), 'ask');
    expect(line).toMatchObject({ pulled: '✕ 1.1K', traded: '✓ 2.0K', hidden: '◆ 12.4K' });
    expect(line?.tip).toContain('◆ 12,400 traded beyond what the book showed, at the prices of hidden sellers.');
    expect(pullsLine(state(), 'bid')?.hidden).toBe('');
  });
});
