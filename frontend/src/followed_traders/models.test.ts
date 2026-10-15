import { describe, expect, it } from 'vitest';
import { activity } from './activity';
import { dayLabel, monthCells, neighbourDay, shiftMonth } from './calendar';
import { asOf, behindStream, capturePill, offAirWhy, onAir } from './capture';
import { capture, closed, day, T, trade } from './followedTestData';
import { judgeReads, readAt } from './proof';
import { doubledRead, gluedRead, tickerUnsettled } from './ticker';
import { toastStep, tradeToasts } from './toastModel';
import type { FollowedRead } from './types';

describe('capture pill', () => {
  it('reads live with how far behind the stream, and each other state in words', () => {
    expect(behindStream(capture())).toBe(6);
    expect(capturePill(day())).toEqual({ tone: 'live', text: 'Live · 6s behind the stream · bar read 10:09:54 ET' });
    expect(capturePill(day({ capture: capture({ bar_visible: false }) }))!.tone).toBe('warn');
    expect(capturePill(day({ capture: capture({ live: false }) }))!.text).toBe('Waiting for the stream');
    expect(capturePill(day({ capture: capture({ age_sec: 125, problem: 'the source wants a sign-in' }) }))).toEqual({
      tone: 'down', text: 'Capture stopped · last read 10:09:54 ET · the source wants a sign-in' });
    expect(capturePill(day({ capture: null }))!.text).toMatch(/not reported/);
    expect(capturePill(day({ feed: { state: 'unreachable', error: 'timed out after 3 s' } }))).toEqual({
      tone: 'down', text: 'The feed is not answering · timed out after 3 s' });
  });

  it('says when the backend started the feed again, and why, for a while after', () => {
    const down = { state: 'unreachable' as const, error: 'could not connect' };
    const ranAt = Date.UTC(2026, 9, 15, 1, 15, 55) / 1000; // 21:15:55 ET
    const keeper = { task: 'Feed Task', next_at: null,
      last: { at: ranAt, why: 'the feed did not answer for 30 s', ok: true, error: null } };
    const pill = capturePill(day({ feed: down, keeper, generated_at: ranAt + 60 }))!;
    expect(pill.text).toBe('The feed is not answering · could not connect · Nova started Feed Task 21:15:55 ET');
    expect(pill.title).toBe(`${pill.text}
Nova ran Feed Task because the feed did not answer for 30 s`);
    // Stale after FOLLOWED_KEEPER_SHOWN_SEC: the pill says only what is true now.
    expect(capturePill(day({ feed: down, keeper, generated_at: ranAt + 901 }))).toEqual({
      tone: 'down', text: 'The feed is not answering · could not connect' });
    // Task Scheduler refused: said with its words.
    const refused = { ...keeper, last: { ...keeper.last, ok: false, error: 'ERROR: no such task' } };
    expect(capturePill(day({ feed: down, keeper: refused, generated_at: ranAt + 60 }))!.text)
      .toBe('The feed is not answering · could not connect · Nova could not start Feed Task: ERROR: no such task');
    // A stopped capture the backend started again says so too.
    const stopped = capturePill(day({ capture: capture({ age_sec: 900 }), keeper, generated_at: ranAt + 60 }))!;
    expect(stopped.text).toBe('Capture stopped · last read 10:09:54 ET · Nova started Feed Task 21:15:55 ET');
    // A backend without the keeper sends none.
    expect(capturePill(day({ feed: down }))!.title).toBeUndefined();
  });

  it("warns when the bar read is the stream's past, never Live", () => {
    // 2026-10-14: the feed read the stream 29 minutes behind; the pill said Live and every slot "Their slot now".
    expect(capturePill(day({ capture: capture({ clock: '09:40:00' }) }))).toEqual({
      tone: 'warn', text: 'Reading 30m 00s behind the stream · bar read 09:40:00 ET · positions shown are from then' });
    // Up to 30 s behind is the stream's own latency: still live.
    expect(capturePill(day({ capture: capture({ clock: '10:09:30' }) }))!.tone).toBe('live');
    // An hour or more behind is still the past, never Live (PR #951 review).
    expect(capturePill(day({ capture: capture({ clock: '08:10:00' }) }))!.text)
      .toBe('Reading 2h 00m behind the stream · bar read 08:10:00 ET · positions shown are from then');
    // A frame from before midnight read after it is 20 s behind, not a day; a screen clock a little ahead is skew.
    const afterMidnight = Date.UTC(2026, 9, 14, 4, 0, 10) / 1000; // 00:00:10 ET
    expect(behindStream(capture({ clock: '23:59:50', updated_at: afterMidnight }))).toBe(20);
    expect(behindStream(capture({ clock: '10:10:30' }))).toBe(0);
  });
});

describe('the stream on air', () => {
  it('is on air only while the feed reads it live, and says why not otherwise', () => {
    expect(onAir(capture())).toBe(true);
    expect(onAir(null)).toBe(false);
    // The feed's last status still says live, five hours after its last read: the stream is over.
    const ended = capture({ clock: '15:57:12', age_sec: 18_000 });
    expect(onAir(ended)).toBe(false);
    expect(offAirWhy(ended)).toBe('last read 15:57:12 ET');
    expect(offAirWhy(capture({ age_sec: 400, problem: 'not live right now' })))
      .toBe('last read 10:09:54 ET · not live right now');
    expect(offAirWhy(capture({ clock: null, age_sec: null, updated_at: null, problem: 'YouTube wants a sign-in' })))
      .toBe('the feed is not reading a live stream right now · YouTube wants a sign-in');
    expect(onAir(capture({ live: false }))).toBe(false);
    expect(offAirWhy(capture({ live: false }))).toBe('Waiting for the stream');
    // No time to prove it is live is not on air.
    expect(onAir(capture({ updated_at: null, age_sec: null }))).toBe(false);
  });

  it('ages the last answer while no new one comes, so a silent backend never keeps the stream on air', () => {
    const got = 1_000_000;
    expect(asOf(day(), got, got).capture!.age_sec).toBe(2);
    expect(onAir(asOf(day(), got, got + 30_000).capture)).toBe(true);
    const later = asOf(day(), got, got + 61_000).capture!;
    expect(later.age_sec).toBe(63);
    expect(onAir(later)).toBe(false);
    expect(asOf(day(), null, got + 61_000).capture!.age_sec).toBe(2);
  });
});

describe('activity', () => {
  it('lists opens, adds and closes newest first, with what the feed did not see said', () => {
    const items = activity(day().traders);
    expect(items.map((i) => `${i.trader} ${i.verb} ${i.symbol}`)).toEqual([
      'ALPHA closed EFGH', 'ALPHA opened ABCD', 'BRAVO closed TQQQ', 'ALPHA opened EFGH', 'BRAVO holding TQQQ',
    ]);
    const bravoOut = items.find((i) => i.key === 'c2|out')!;
    expect(bravoOut.note).toBe('Held ≥ 5m 00s · Somewhere between 09:45:00 and 09:59:00');
    expect(items.find((i) => i.key === 'c2|in')!.note).toBe('Already open when capture started');
    const added = activity([{ ...day().traders[0], closed: [],
      open: [trade({ id: 'a', adds: [{ ts: T + 60, price: 1.95, prev_price: 2 }] })] }]);
    expect(added[0]).toMatchObject({ verb: 'added to', price: 1.95, note: 'Average 2.00 → 1.95', image: null });
  });
});

describe('proof', () => {
  const read = (sec: number, positions: FollowedRead['positions'], seen = true): FollowedRead =>
    ({ ts: T + sec, until_ts: null, seen, positions, unparsed: [] });
  const held = [{ side: 'long' as const, symbol: 'ABCD', price: 2 }];

  it('marks every read during the trade that differed from what was logged as ignored', () => {
    const t = closed({ symbol: 'ABCD' });
    const reads = [
      read(-10, []), read(0, held), read(30, [{ side: 'long', symbol: 'ABC', price: 12 }]), read(32, held),
      read(100, [], false), read(102, held), read(300, []),
    ];
    const { reads: judged, ignored } = judgeReads(t, reads);
    expect(judged.map((r) => r.verdict)).toEqual(['before', 'entry', 'ignored', 'held', 'not_seen', 'held', 'exit']);
    expect(ignored).toBe(1);
    expect(readAt(reads, T + 31)!.ts).toBe(T + 30);
  });

  it('follows the average after an add', () => {
    const t = trade({ adds: [{ ts: T + 50, price: 1.9, prev_price: 2 }] });
    const reads = [read(0, held), read(50, [{ side: 'long', symbol: 'ABCD', price: 1.9 }]), read(60, held)];
    expect(judgeReads(t, reads).reads.map((r) => r.verdict)).toEqual(['entry', 'held', 'ignored']);
  });

  it('counts a read of the ticker glued to its price as the trade, not an ignored read', () => {
    // The bar's "XYZI 14.03" read XYZ 114.03: the same position, read wrong.
    const t = trade({ symbol: 'XYZI', side: 'short', entry: { first_price: 14.03, avg_price: 14.03, ts: T, since_ts: null, known: true } });
    const reads = [read(0, [{ side: 'short', symbol: 'XYZI', price: 14.03 }]), read(2, [{ side: 'short', symbol: 'XYZ', price: 114.03 }]),
      read(4, [{ side: 'short', symbol: 'XYZ', price: 14.03 }])];
    expect(judgeReads(t, reads).reads.map((r) => r.verdict)).toEqual(['entry', 'held', 'ignored']);
  });

  it('counts a read with the last letter read twice as the trade (RGTI 12.08 read RGTI 112.08, 2026-10-15)', () => {
    const t = trade({ symbol: 'RGTI', entry: { first_price: 12.08, avg_price: 12.08, ts: T, since_ts: null, known: true } });
    const reads = [read(0, [{ side: 'long', symbol: 'RGTI', price: 12.08 }]), read(2, [{ side: 'long', symbol: 'RGTI', price: 112.08 }]),
      read(4, [{ side: 'long', symbol: 'RGT', price: 112.08 }]), read(6, [{ side: 'long', symbol: 'RGTI', price: 12.5 }])];
    expect(judgeReads(t, reads).reads.map((r) => r.verdict)).toEqual(['entry', 'held', 'held', 'ignored']);
  });
});

describe('a ticker glued to its price', () => {
  it('reads a ticker glued to its price as OCR does, and says when nothing may be priced', () => {
    expect(gluedRead('XYZI', 14.03)).toEqual({ symbol: 'XYZ', price: 114.03 });
    expect(gluedRead('BAS', 1.2)).toEqual({ symbol: 'BA', price: 51.2 });
    expect(gluedRead('ABCI', 0.5432)).toEqual({ symbol: 'ABC', price: 10.5432 });
    expect(gluedRead('NVDL', 35.41)).toBeNull();
    expect(doubledRead('RGTI', 12.08)).toEqual({ symbol: 'RGTI', price: 112.08 });
    expect(doubledRead('ABCS', 5.2)).toEqual({ symbol: 'ABCS', price: 55.2 });
    expect(doubledRead('NVDL', 35.41)).toBeNull();
    expect(doubledRead('ABCO', 1.5)).toBeNull();
    const ticker ={ read_symbol: 'XYZ', read_price: 114.03, other_symbol: 'XYZI', other_price: 14.03, why: null };
    expect(tickerUnsettled(trade({ ticker: { ...ticker, state: 'checking' } }))).toBe(true);
    expect(tickerUnsettled(trade({ ticker: { ...ticker, state: 'unchecked' } }))).toBe(true);
    expect(tickerUnsettled(trade({ ticker: { ...ticker, state: 'corrected' } }))).toBe(false);
    expect(tickerUnsettled(trade())).toBe(false);   // an older backend sends no ticker
  });
});

describe('calendar', () => {
  it('draws October 2026 with dots, weekends and no future', () => {
    const cells = monthCells(2026, 9, { today: '2026-10-13', withTrades: new Set(['2026-10-13']), picked: '2026-10-13' });
    expect(cells.slice(0, 4)).toEqual([null, null, null, null]);
    const c13 = cells.find((c) => c?.day === 13)!;
    expect(c13).toMatchObject({ hasTrades: true, today: true, picked: true, weekend: false, future: false });
    expect(cells.find((c) => c?.day === 17)).toMatchObject({ weekend: true, future: true });
    expect(dayLabel('2026-10-13')).toBe('Tue, Oct 13');
    expect(shiftMonth(2026, 0, -1)).toEqual({ year: 2025, month: 11 });
    expect(neighbourDay(['2026-10-13', '2026-10-09', '2026-10-12'], '2026-10-12', -1)).toBe('2026-10-09');
    expect(neighbourDay(['2026-10-13', '2026-10-09'], '2026-10-13', 1)).toBeNull();
  });
});

describe('toasts', () => {
  it('raises nothing on the first answer, then opens, adds and closes', () => {
    const first = day();
    expect(tradeToasts(null, first)).toEqual([]);
    const next = day();
    const alpha = next.traders[0];
    alpha.open = [{ ...alpha.open[0], adds: [{ ts: T + 610, price: 1.95, prev_price: 2 }] },
      trade({ id: 'n1', symbol: 'NEW', entry: { first_price: 3.1, avg_price: 3.1, ts: T + 620, since_ts: null, known: true } })];
    next.traders[1].open = [trade({ id: 'n2', trader: 'BRAVO', entry: { ...trade().entry, known: false } })];
    const moved = day();
    moved.traders[0].open = [];
    moved.traders[0].closed = [closed({ id: 'o1', exit: { ...closed().exit!, to_ts: T + 700 } }), ...moved.traders[0].closed];
    expect(tradeToasts(first, next).map((t) => `${t.verb} ${t.symbol} ${t.price}`)).toEqual([
      'added to ABCD 1.95', 'opened NEW 3.1']);
    expect(tradeToasts(first, moved).map((t) => `${t.trader} ${t.verb} ${t.symbol}`)).toEqual(['ALPHA closed ABCD']);
    expect(tradeToasts(first, day({ date: '2026-10-14' }))).toEqual([]);
  });

  it('waits for a ticker being checked, so the toast names the ticker as checked, never the glued one', () => {
    const ticker = { read_symbol: 'XYZ', read_price: 114.03, other_symbol: 'XYZI', other_price: 14.03, why: 'reading' };
    const entry = { first_price: 114.03, avg_price: 114.03, ts: T + 590, since_ts: null, known: true };
    const withTrade = (t: ReturnType<typeof trade>, at: number) => {
      const d = day({ generated_at: at });
      d.traders[0].open = [...d.traders[0].open, t];
      return d;
    };
    const checking = trade({ id: 'ALPHA|short|XYZ|1', symbol: 'XYZ', side: 'short', entry, ticker: { ...ticker, state: 'checking' } });
    const fixed = { ...checking, symbol: 'XYZI', entry: { ...entry, first_price: 14.03, avg_price: 14.03 },
      ticker: { ...ticker, state: 'corrected' as const, why: 'the ticker was read glued to its price' } };
    const first = day();
    const waiting = withTrade(checking, T + 600);
    const step = toastStep(first, waiting);
    expect(step.toasts).toEqual([]);                                                   // not news yet
    expect([...step.held]).toEqual([checking.id]);
    const settled = toastStep(waiting, withTrade(fixed, T + 605), step.held);
    expect(settled.toasts.map((t) => `${t.verb} ${t.symbol} ${t.price} ${t.check}`)).toEqual(['opened XYZI 14.03 null']);
    expect(settled.held.size).toBe(0);
    // Still checking a minute after the entry: raised, saying the ticker is not checked.
    const late = toastStep(waiting, withTrade(checking, T + 650), step.held);
    expect(late.toasts.map((t) => `${t.verb} ${t.symbol} ${t.check}`)).toEqual(['opened XYZ reading']);
    expect(toastStep(withTrade(checking, T + 650), withTrade(fixed, T + 655), late.held).toasts).toEqual([]); // never twice
  });

  it('never announces a trade twice when its ticker is checked again (PR #972 review)', () => {
    // Announced as read, then checked once more inside its first minute (the feed corrected its ticker, or a restart
    // forgot an answer), then settled: no second "opened", no add or close announced again.
    const ticker = { read_symbol: 'XYZ', read_price: 114.03, other_symbol: 'XYZI', other_price: 14.03, why: 'reading' };
    const entry = { first_price: 114.03, avg_price: 114.03, ts: T + 590, since_ts: null, known: true };
    const asRead = trade({ id: 'ALPHA|short|XYZ|1', symbol: 'XYZ', side: 'short', entry, ticker: { ...ticker, state: 'as_read' },
      adds: [{ ts: T + 595, price: 114.1, prev_price: 114.03 }] });
    const at = (t: ReturnType<typeof trade>, when: number) => {
      const d = day({ generated_at: when });
      d.traders[0].open = [...d.traders[0].open, t];
      return d;
    };
    const announced = toastStep(day(), at(asRead, T + 596));
    expect(announced.toasts.map((t) => t.verb)).toEqual(['opened', 'added to']);
    const again = toastStep(at(asRead, T + 596), at({ ...asRead, ticker: { ...ticker, state: 'checking' } }, T + 600),
      announced.held);
    expect(again.toasts).toEqual([]);
    expect(again.held.size).toBe(0);
    const back = toastStep(at({ ...asRead, ticker: { ...ticker, state: 'checking' } }, T + 600), at(asRead, T + 605), again.held);
    expect(back.toasts).toEqual([]);
    // A trade already there in the first answer, its ticker being checked, is not news when the check ends either.
    const there = at({ ...asRead, ticker: { ...ticker, state: 'checking' } }, T + 600);
    const baseline = toastStep(null, there);
    expect(toastStep(there, at(asRead, T + 605), baseline.held).toasts).toEqual([]);
  });
});
