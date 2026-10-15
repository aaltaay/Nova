import { describe, expect, it } from 'vitest';
import { FT_PL_OLD_BACKEND, FT_PL_WAITING } from './constants';
import { closed, day, RECORD, T, trade } from './followedTestData';
import { dayPl, mergePoints, recordPl, scoredPoints, summarize } from './plSummary';
import type { FollowedRecords, FollowedTrade, FollowedTrader } from './types';

/** A closed trade that exited `at` one price `sec` after T with this P/L %. */
function scored(id: string, sec: number, pct: number, result: 'win' | 'loss' | 'scratch' = pct > 0 ? 'win' : pct < 0 ? 'loss' : 'scratch'): FollowedTrade {
  return closed({ id, result, pl: { per_share: pct / 10, pct },
    exit: { state: 'at', price: 2, low: null, high: null, from_ts: null, to_ts: T + sec, trade_ts: T + sec - 1,
      source: 'ibkr_trades', why: null } });
}

/** An unscored one: its exit seen only in a window, so a low–high P/L and no result but unscored. */
function windowed(id: string, sec: number): FollowedTrade {
  return closed({ id, result: 'unscored',
    pl: { low_per_share: -0.5, high_per_share: 0.9, low_pct: -25, high_pct: 45 },
    exit: { state: 'range', price: null, low: 1.5, high: 2.9, from_ts: T + sec - 60, to_ts: T + sec, trade_ts: null,
      source: 'ibkr_trades', why: null } });
}

function trader(name: string, closedTrades: FollowedTrade[], open: FollowedTrade[] = []): FollowedTrader {
  return { name, face: null, record: RECORD, seen: null, open, closed: closedTrades };
}

function records(traders: FollowedRecords['traders']): FollowedRecords {
  return { schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, range: 'week', from: '2026-10-07',
    to: '2026-10-13', dates: [], pending: 0, overall: RECORD, traders };
}

describe('what a followed trader made, per share in %', () => {
  it('adds up the scored trades oldest exit first, and leaves unscored and open trades out', () => {
    const trades = [scored('c', 300, -0.4), windowed('w', 250), scored('a', 100, 7.5), scored('s', 200, 0),
      closed({ id: 'n', result: 'unscored', pl: null, exit: { state: 'pending', price: null, low: null, high: null,
        from_ts: null, to_ts: T + 400, trade_ts: null, source: null, why: null } })];
    expect(scoredPoints(trades)).toEqual([{ ts: T + 100, pct: 7.5 }, { ts: T + 200, pct: 0 }, { ts: T + 300, pct: -0.4 }]);
    const s = summarize(scoredPoints(trades));
    expect(s.count).toBe(3);
    expect(s.sumPct).toBe(7.1);
    expect(s.avgPct).toBeCloseTo(2.3667, 4);
    expect(s.curve).toEqual([0, 7.5, 7.5, 7.1]);
    // An open position, even one priced now, is not a result yet.
    const open = trade({ id: 'o', now: { state: 'live', price: 3, trade_ts: T, why: null }, pl: { per_share: 1, pct: 50 } });
    expect(dayPl([trader('ALPHA', trades, [open])]).of('ALPHA')!.sumPct).toBe(7.1);
  });

  it('keeps two decimals however many trades it adds', () => {
    const s = summarize([0.1, 0.2, 0.07, -0.21].map((pct, i) => ({ ts: T + i, pct })));
    expect(s.sumPct).toBe(0.16);
    expect(s.curve).toEqual([0, 0.1, 0.3, 0.37, 0.16]);
  });

  it('says nothing was made in an empty span: no trades, no average, a flat line at zero', () => {
    expect(summarize([])).toEqual({ count: 0, sumPct: 0, avgPct: null, curve: [0] });
    const none = dayPl([]);
    expect(none.everyone).toEqual({ count: 0, sumPct: 0, avgPct: null, curve: [0] });
    expect(none.of('ALPHA')!.count).toBe(0);
    expect(recordPl(records([]), null).everyone!.count).toBe(0);
  });

  it('gives a trader with only unscored trades no figure', () => {
    const span = dayPl([trader('BRAVO', [windowed('w1', 100), windowed('w2', 200)])]);
    expect(span.of('BRAVO')).toEqual({ count: 0, sumPct: 0, avgPct: null, curve: [0] });
    expect(span.everyone!.count).toBe(0);
    // The fixture's BRAVO: one unscored trade.
    expect(dayPl(day().traders).of('BRAVO')!.count).toBe(0);
  });

  it("makes Everyone's figure the traders' trades together", () => {
    const traders = [
      trader('ALPHA', [scored('a1', 100, 0.3), scored('a2', 400, -0.85), windowed('aw', 300)]),
      trader('BRAVO', [scored('b1', 200, 40.5), scored('b2', 500, -4.25)]),
      trader('CHARLIE', [windowed('cw', 250)]),
    ];
    const span = dayPl(traders);
    const each = ['ALPHA', 'BRAVO', 'CHARLIE'].map((n) => span.of(n)!);
    expect(each.map((s) => s.sumPct)).toEqual([-0.55, 36.25, 0]);
    expect(span.everyone!.count).toBe(each.reduce((n, s) => n + s.count, 0));
    expect(span.everyone!.sumPct).toBe(35.7);
    expect(span.everyone!.curve).toEqual([0, 0.3, 40.8, 39.95, 35.7]);
    // From the record route the same trades give the same figures.
    const fromRecord = recordPl(records(traders.map((t) => ({ name: t.name, record: RECORD, scored: scoredPoints(t.closed) }))), null);
    expect(fromRecord.everyone).toEqual(span.everyone);
    expect(fromRecord.of('BRAVO')).toEqual(span.of('BRAVO'));
    expect(mergePoints([[{ ts: 3, pct: 1 }], [{ ts: 1, pct: 2 }, { ts: 2, pct: 3 }]]).map((p) => p.ts)).toEqual([1, 2, 3]);
  });

  it('says why a Week or All span has no figure: still read, or a backend that sends none', () => {
    expect(recordPl(null, null)).toMatchObject({ everyone: null, why: FT_PL_WAITING });
    expect(recordPl(null, 'HTTP 500')).toMatchObject({ everyone: null, why: 'HTTP 500' });
    const old = recordPl(records([{ name: 'ALPHA', record: RECORD }]), null);
    expect(old).toMatchObject({ everyone: null, why: FT_PL_OLD_BACKEND });
    expect(old.of('ALPHA')).toBeNull();
  });
});
