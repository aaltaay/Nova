import { describe, expect, it } from 'vitest';
import { activity } from './activity';
import { dayLabel, monthCells, neighbourDay, shiftMonth } from './calendar';
import { asOf, behindStream, capturePill, offAirWhy, onAir } from './capture';
import { capture, closed, day, T, trade } from './followedTestData';
import { judgeReads, readAt } from './proof';
import { tradeToasts } from './toastModel';
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

  it("warns when the bar read is the stream's past, never Live", () => {
    // 2026-10-14: the feed read the stream 29 minutes behind; the pill said Live and every slot "Their slot now".
    expect(capturePill(day({ capture: capture({ clock: '09:40:00' }) }))).toEqual({
      tone: 'warn', text: 'Reading 30m 00s behind the stream · bar read 09:40:00 ET · positions shown are from then' });
    // Up to 30 s behind is the stream's own latency: still live.
    expect(capturePill(day({ capture: capture({ clock: '10:09:30' }) }))!.tone).toBe('live');
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
});
