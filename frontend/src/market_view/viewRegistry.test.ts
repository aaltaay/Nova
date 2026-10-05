import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  VIEW_SILENT_LOCK_MS,
  VIEW_TRANSIT_LOCK_MS,
  VIEW_UNDRAWN_LOCK_MS,
} from '../constantGroups/market_view';
import {
  currentViewLock,
  forgetBook,
  noteBeat,
  noteBookFrame,
  noteBookShown,
  noteQuote,
  noteSubscribed,
  recomputeViewLocks,
  resetViewRegistryForTests,
  subscribeViewLocks,
  viewLockReason,
  viewStampFor,
} from './viewRegistry';

// 2026-10-05 08:30 ET: the Level 2 on screen was 3-7 s behind Nova's book and the operator sold at a
// bid that no longer existed. While a view lags, its orders lock (ADR 045).
const T0 = 1_791_203_400_000;

afterEach(() => resetViewRegistryForTests());

function live(symbol = 'APUS', at = T0) {
  noteSubscribed(symbol, 'proc-1', at);
  noteBookFrame(symbol, { seq: 1, at: at / 1000 - 0.01, sent: at / 1000 - 0.005 }, at);
  noteBookShown(symbol, 1, 6.58, 6.65);
}

describe('the view lock', () => {
  it('is open while the backend speaks and the newest book is drawn', () => {
    live();
    noteBeat('APUS', { seq: 1, now: (T0 + 250) / 1000 }, T0 + 260);
    expect(viewLockReason('APUS', T0 + 400)).toBeNull();
  });

  it('locks when the line has gone quiet: a stalled socket, not a quiet book (beats keep a quiet book live)', () => {
    live();
    expect(viewLockReason('APUS', T0 + VIEW_SILENT_LOCK_MS - 1)).toBeNull();
    expect(viewLockReason('APUS', T0 + VIEW_SILENT_LOCK_MS + 50)).toMatch(/no word from Nova/);
  });

  it('locks when a frame took too long to arrive (a socket replaying a backlog)', () => {
    live();
    noteBookFrame('APUS', { seq: 2, at: T0 / 1000, sent: T0 / 1000 }, T0 + VIEW_TRANSIT_LOCK_MS + 200);
    noteBookShown('APUS', 2, 6.56, 6.65);
    expect(viewLockReason('APUS', T0 + VIEW_TRANSIT_LOCK_MS + 210)).toMatch(/took 0\.7 s to arrive/);
  });

  it('locks when a newer book waits too long to be drawn', () => {
    live();
    noteBeat('APUS', { seq: 4, now: T0 / 1000 }, T0 + 10);       // the backend has version 4; the ladder drew 1
    expect(viewLockReason('APUS', T0 + VIEW_UNDRAWN_LOCK_MS - 20)).toBeNull();
    expect(viewLockReason('APUS', T0 + VIEW_UNDRAWN_LOCK_MS + 50)).toMatch(/not drawn its newest book/);
    noteBookFrame('APUS', { seq: 4, at: T0 / 1000, sent: T0 / 1000 + 0.6 }, T0 + 610);
    noteBookShown('APUS', 4, 6.5, 6.55);
    expect(viewLockReason('APUS', T0 + 620)).toBeNull();
  });

  it('judges nothing for a symbol whose Level 2 is not on screen here (the backend still does)', () => {
    expect(viewLockReason('NONE', T0)).toBeNull();
    live();
    forgetBook('APUS');
    expect(viewLockReason('APUS', T0 + 10_000)).toBeNull();
  });

  it('tells readers only when a lock flips', () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(T0);
      live('APUS', T0);
      const flips: (string | null)[] = [];
      const off = subscribeViewLocks(() => flips.push(currentViewLock('APUS')));
      recomputeViewLocks(T0 + 100);
      recomputeViewLocks(T0 + VIEW_SILENT_LOCK_MS + 100);
      recomputeViewLocks(T0 + VIEW_SILENT_LOCK_MS + 300);         // still locked: no second notice
      expect(flips).toHaveLength(1);
      expect(flips[0]).toMatch(/no word from Nova/);
      off();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('the view an order carries', () => {
  it('names the drawn book, the quote and the backend process', () => {
    live();
    noteQuote('APUS', { seq: 9, at: T0 / 1000, price: 6.6 });
    const stamp = viewStampFor('apus', T0 + 100, T0 + 100);
    expect(stamp).toMatchObject({
      schema_version: 1,
      symbol: 'APUS',
      action_wall_ms: T0 + 100,
      instance: 'proc-1',
      book: { seq: 1, bid: 6.58, ask: 6.65 },
      quote: { seq: 9, price: 6.6 },
    });
    expect(stamp.desk?.silent_ms).toBe(100);
  });

  it('says no book when Level 2 never drew one', () => {
    noteSubscribed('APUS', 'proc-1', T0);
    noteBookFrame('APUS', { seq: 3, at: T0 / 1000, sent: T0 / 1000 }, T0);
    expect(viewStampFor('APUS', T0, T0).book).toBeNull();
  });
});
