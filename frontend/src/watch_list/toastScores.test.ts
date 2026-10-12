/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  dueForScore,
  getToastScores,
  recordHeld,
  recordToast,
  resetToastScoresForTests,
  scoreFromBars,
  scorePendingToasts,
  summarizeToasts,
  type MinuteBar,
  type ToastRecord,
  type ToastScoresDoc,
} from './toastScores';
import { WATCH_TOAST_SCORES_KEY, WATCH_TOAST_SCORE_GIVE_UP_MS } from './watchListConstants';

/** 2026-09-23 10:14:05 ET: the toast. Its minute is 10:14; the fifth after it is 10:19. */
const AT = Date.UTC(2026, 8, 23, 14, 14, 5);
const MIN = (Date.UTC(2026, 8, 23, 14, 14, 0)) / 1000;
const bar = (minutesFromToastMinute: number, c: number): MinuteBar => ({ t: MIN + minutesFromToastMinute * 60, c });

function record(patch: Partial<ToastRecord> = {}): ToastRecord {
  return { id: 'GRML-hod-1', symbol: 'GRML', kind: 'hod', at: AT, price: 4.0, score: null, ...patch };
}

describe('scoreFromBars', () => {
  it("is the fifth minute's close against the toast's price", () => {
    const bars = [bar(-1, 3.9), bar(0, 4.0), bar(3, 4.2), bar(5, 4.4), bar(6, 9.9)];
    const score = scoreFromBars(record(), bars);
    expect(score).toEqual({ ref: 4.0, after: 4.4, move: expect.closeTo(0.1, 6) });
  });

  it("uses the minute before the toast when the toast showed no price, and the last close when no trade since", () => {
    const bars = [bar(-2, 3.5), bar(-1, 4.0), bar(2, 3.0), bar(7, 3.1)];
    expect(scoreFromBars(record({ price: null }), bars)).toEqual({ ref: 4.0, after: 3.0, move: -0.25 });
  });

  it('waits while the bars do not reach the fifth minute or back to the toast; the last try scores what there is', () => {
    expect(scoreFromBars(record(), [bar(-1, 3.9), bar(2, 4.1)])).toBeNull();           // history still lagging
    expect(scoreFromBars(record(), [bar(2, 4.1), bar(6, 4.2)])).toBeNull();            // the read starts after the toast
    expect(scoreFromBars(record(), [bar(-1, 3.9), bar(2, 4.1)], true)).toEqual({ ref: 4.0, after: 4.1, move: expect.closeTo(0.025, 6) });
    expect(scoreFromBars(record(), [bar(2, 4.1)], true)).toEqual({ none: 'no bars' });
  });

  it('is due once the fifth minute has closed and settled, and never twice', () => {
    expect(dueForScore(record(), AT + 5 * 60_000)).toBe(false);
    expect(dueForScore(record(), AT + 8 * 60_000)).toBe(true);
    expect(dueForScore(record({ score: { none: 'no bars' } }), AT + 8 * 60_000)).toBe(false);
  });
});

describe('summarizeToasts', () => {
  it('counts each kind, how many scored, how many were higher, and the median move', () => {
    const doc: ToastScoresDoc = {
      schema_version: 1, day: '2026-09-23', held: {},
      toasts: [
        record({ id: 'a', score: { ref: 1, after: 1.1, move: 0.1 } }),
        record({ id: 'b', score: { ref: 1, after: 0.9, move: -0.1 } }),
        record({ id: 'c', score: { ref: 1, after: 0.95, move: -0.05 } }),
        record({ id: 'd', score: { none: 'no bars' } }),
        record({ id: 'e', kind: 'join', score: null }),
      ],
    };
    expect(summarizeToasts(doc)).toEqual([
      { kind: 'join', toasts: 1, scored: 0, higher: 0, medianMove: null },
      { kind: 'hod', toasts: 4, scored: 3, higher: 1, medianMove: -0.05 },
    ]);
  });
});

describe("the day's record", () => {
  beforeEach(() => {
    localStorage.clear();
    resetToastScoresForTests();
    vi.useFakeTimers({ now: AT, toFake: ['Date'] });
  });
  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
    resetToastScoresForTests();
  });

  it('keeps toasts and held counts in localStorage for the trading day, and starts fresh the next', () => {
    recordToast('GRML', 'hod', 4.52, AT);
    recordHeld('running_up', AT);
    recordHeld('running_up', AT);
    resetToastScoresForTests();                       // a reload: read back from storage
    const saved = JSON.parse(localStorage.getItem(WATCH_TOAST_SCORES_KEY) ?? '{}') as ToastScoresDoc;
    expect(saved.day).toBe('2026-09-23');
    expect(getToastScores().toasts.map(t => [t.symbol, t.kind, t.price])).toEqual([['GRML', 'hod', 4.52]]);
    vi.setSystemTime(Date.UTC(2026, 8, 24, 8, 30));     // 04:30 ET the next day
    expect(getToastScores().toasts).toEqual([]);
  });

  it('drops a record of an unknown version and says so', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(WATCH_TOAST_SCORES_KEY, JSON.stringify({ schema_version: 9, day: '2026-09-23', toasts: [{}], held: {} }));
    expect(getToastScores().toasts).toEqual([]);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('scores what is due with one read per symbol, skips a replay answer, and gives up after 30 minutes', async () => {
    recordToast('GRML', 'hod', 4.0, AT);
    recordToast('GRML', 'armed', 4.0, AT + 1_000);
    recordToast('ONCO', 'join', null, AT);
    const bars = [bar(-1, 3.9), bar(0, 4.0), bar(5, 4.4), bar(6, 4.5)];
    const read = vi.fn(async (symbol: string) => ({ bars, replay: symbol === 'ONCO' }));
    const later = AT + 8 * 60_000;
    vi.setSystemTime(later);
    await scorePendingToasts(later, read);
    expect(read).toHaveBeenCalledTimes(2);
    const scored = getToastScores().toasts;
    expect(scored.filter(t => t.symbol === 'GRML').map(t => t.score)).toEqual([
      { ref: 4.0, after: 4.4, move: expect.closeTo(0.1, 6) },
      { ref: 4.0, after: 4.4, move: expect.closeTo(0.1, 6) },
    ]);
    expect(scored.find(t => t.symbol === 'ONCO')?.score).toBeNull();     // the Sim's bars are not today's tape
    const giveUp = AT + WATCH_TOAST_SCORE_GIVE_UP_MS + 60_000;
    vi.setSystemTime(giveUp);
    await scorePendingToasts(giveUp, read);
    expect(getToastScores().toasts.find(t => t.symbol === 'ONCO')?.score).toEqual({ none: 'no bars' });
  });
});
