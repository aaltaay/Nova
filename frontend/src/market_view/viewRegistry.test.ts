import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  VIEW_SILENT_LOCK_MS,
  VIEW_TRANSIT_LOCK_MS,
  VIEW_UNDRAWN_LOCK_MS,
} from '../constantGroups/market_view';
import {
  currentViewLock,
  forgetBackendGate,
  forgetBook,
  noteBackendGate,
  noteBeat,
  noteBookFrame,
  noteBookShown,
  noteQuote,
  noteRefused,
  noteSubscribed,
  onViewLockFlip,
  recomputeViewLocks,
  resetViewRegistryForTests,
  subscribeViewLocks,
  viewLockLabel,
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

describe('a Level 2 IBKR refused (operator decision 2026-10-13, #913: lock, with the true reason)', () => {
  const WHY = 'IBKR refused this Level 2 (IB error 309): all 3 of its Level 2 lines are in use.';

  it('locks at once with the words IBKR gave, not "behind", whatever the socket says next', () => {
    noteSubscribed('VLO', 'proc-1', T0);
    noteRefused('VLO', WHY);
    noteSubscribed('VLO', 'proc-1', T0 + 1_200); // the retry, said before IBKR answers again
    const why = viewLockReason('VLO', T0 + 1_300);
    expect(why).toBe(`No Level 2 for VLO: ${WHY} Orders are locked until a Level 2 is live. Flatten and cancels still work.`);
    expect(viewLockLabel(why!)).toBe('No Level 2 · locked');
  });

  it('opens on the first book', () => {
    noteRefused('VLO', WHY);
    noteBookFrame('VLO', { seq: 1, at: T0 / 1000, sent: T0 / 1000 }, T0);
    expect(viewLockReason('VLO', T0 + 100)).toBeNull();
  });

  it('tells the backend log each flip: locked with its reason, then open with how long it was locked', () => {
    const flips: Array<[string, string | null, number | null]> = [];
    onViewLockFlip((symbol, why, lockedFor) => flips.push([symbol, why, lockedFor]));
    const stop = subscribeViewLocks(() => {});
    noteRefused('VLO', WHY);
    recomputeViewLocks(T0);
    recomputeViewLocks(T0 + 400); // still locked, same reason: no second report
    noteBookFrame('VLO', { seq: 1, at: T0 / 1000, sent: (T0 + 3_000) / 1000 }, T0 + 3_000);
    noteBookShown('VLO', 1, 456, 457);
    recomputeViewLocks(T0 + 3_000);
    stop();
    expect(flips).toHaveLength(2);
    expect(flips[0][0]).toBe('VLO');
    expect(flips[0][1]).toContain('No Level 2 for VLO');
    expect(flips[1]).toEqual(['VLO', null, 3_000]);
  });

  it('a lock that turns from no Level 2 into a Level 2 behind is a new reason on the button', () => {
    const flips: Array<string | null> = [];
    onViewLockFlip((_s, why) => flips.push(why));
    noteSubscribed('APUS', 'proc-1', T0);
    noteRefused('APUS', WHY);
    recomputeViewLocks(T0);
    noteBookFrame('APUS', { seq: 1, at: T0 / 1000, sent: T0 / 1000 }, T0); // a book, then silence
    recomputeViewLocks(T0 + VIEW_SILENT_LOCK_MS + 100);
    expect(flips.map((w) => (w ? viewLockLabel(w) : null))).toEqual(['No Level 2 · locked', 'Market view behind · locked']);
    expect(currentViewLock('APUS')).toContain('behind the market');
  });
});

// 2026-10-14 09:25:19 ET: GENK's Time & Sales had missed every trade for 8 s and the order went out anyway.
describe("the backend's own lock (ADR 045 amendment 2026-10-14)", () => {
  const TAPE = {
    code: 'TAPE_STALE',
    text: "GENK's Time & Sales is missing trades: its last print came at 09:25:11 ET. New orders on it wait until "
      + 'its prints are back. Flatten and cancels still work.',
  };

  it("locks with the door's own words, Level 2 or not, and opens when the backend says so", () => {
    const flips: Array<[string, string | null]> = [];
    onViewLockFlip((symbol, why) => flips.push([symbol, why]));
    noteBackendGate('genk', TAPE);
    expect(viewLockReason('GENK')).toBe(TAPE.text);
    expect(currentViewLock('GENK')).toBe(TAPE.text);
    expect(viewLockLabel(TAPE.text)).toBe('Time & Sales behind · locked');
    noteBackendGate('GENK', null);
    expect(currentViewLock('GENK')).toBeNull();
    expect(flips).toEqual([['GENK', TAPE.text], ['GENK', null]]);
  });

  it('comes before a live Level 2 and names a feed lock as Nova behind', () => {
    live('GENK');
    const feed = { code: 'FEED_STALE', text: 'Nova is behind the market right now. Flatten and cancels still work.' };
    noteBackendGate('GENK', feed);
    expect(viewLockReason('GENK', T0 + 10)).toBe(feed.text);
    expect(viewLockLabel(feed.text)).toBe('Nova behind the market · locked');
  });

  it('keeps its last answer for an older backend and forgets it when the socket closes', () => {
    noteBackendGate('GENK', TAPE);
    noteBackendGate('GENK', undefined);          // a ping without `gate`: an older backend
    expect(currentViewLock('GENK')).toBe(TAPE.text);
    forgetBackendGate('GENK');
    expect(currentViewLock('GENK')).toBeNull();
  });
});

describe('a Level 2 that is open with no book yet (operator decision 2026-10-27, #913 option 1)', () => {
  // BKYI 2026-10-13: IBKR never answered the request; the socket said subscribed and beat every 250 ms.
  const WAIT = "No book yet on BKYI's Level 2. Orders are locked until its first book arrives. Flatten and cancels still work.";

  it('locks while only subscribed and beats arrive, however timely', () => {
    noteSubscribed('BKYI', 'proc-1', T0);
    for (let i = 1; i <= 8; i += 1) {
      noteBeat('BKYI', { seq: 0, now: (T0 + i * 250) / 1000, first_book: { state: 'waiting', overdue: false } }, T0 + i * 250);
    }
    const why = viewLockReason('BKYI', T0 + 2_010);
    expect(why).toBe(WAIT);
    expect(viewLockLabel(why!)).toBe('Waiting for Level 2 · locked');
  });

  it('locks on an older backend whose beats carry no first_book at all', () => {
    noteSubscribed('BKYI', 'proc-1', T0);
    noteBeat('BKYI', { seq: 0, now: (T0 + 250) / 1000 }, T0 + 250);
    expect(viewLockReason('BKYI', T0 + 300)).toBe(WAIT);
  });

  it("names what IBKR has done once the backend's wait is overdue", () => {
    noteSubscribed('BKYI', 'proc-1', T0);
    const text = "IBKR has not answered BKYI's Level 2 request in 5 s.";
    noteBeat('BKYI', { seq: 0, now: (T0 + 6_000) / 1000, first_book: { state: 'unanswered', overdue: true, text } }, T0 + 6_000);
    expect(viewLockReason('BKYI', T0 + 6_010)).toBe(
      `No book yet on BKYI's Level 2. ${text} Orders are locked until its first book arrives. Flatten and cancels still work.`,
    );
  });

  it('opens on the first book frame', () => {
    noteSubscribed('BKYI', 'proc-1', T0);
    noteBookFrame('BKYI', { seq: 1, at: (T0 + 990) / 1000, sent: (T0 + 995) / 1000 }, T0 + 1_000);
    noteBookShown('BKYI', 1, 2.1, 2.12);
    expect(viewLockReason('BKYI', T0 + 1_010)).toBeNull();
  });

  it('opens when the backend says the line already has its book (another viewer holds it)', () => {
    noteSubscribed('BKYI', 'proc-1', T0);
    noteBeat('BKYI', { seq: 3, now: (T0 + 250) / 1000, first_book: null }, T0 + 250);
    expect(viewLockReason('BKYI', T0 + 260)).toBeNull();
  });

  it('locks again on every reconnect: a book from the earlier socket does not count', () => {
    live('BKYI');
    expect(viewLockReason('BKYI', T0 + 10)).toBeNull();
    noteSubscribed('BKYI', 'proc-1', T0 + 2_000);   // the socket reconnected
    expect(viewLockReason('BKYI', T0 + 2_010)).toBe(WAIT);
  });

  it('keeps a refused line its own words', () => {
    noteSubscribed('BKYI', 'proc-1', T0);
    noteRefused('BKYI', 'IBKR refused this Level 2 (IB error 309).');
    noteSubscribed('BKYI', 'proc-1', T0 + 1_200);
    expect(viewLockLabel(viewLockReason('BKYI', T0 + 1_300)!)).toBe('No Level 2 · locked');
  });

  it("labels the backend's BOOK_WAITING lock the same way", () => {
    const text = "BKYI's Level 2 is open but has sent no book yet. New orders on it wait for its first book. Flatten and cancels still work.";
    noteBackendGate('BKYI', { code: 'BOOK_WAITING', text });
    expect(viewLockReason('BKYI', T0)).toBe(text);
    expect(viewLockLabel(text)).toBe('Waiting for Level 2 · locked');
  });
});
