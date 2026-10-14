/** Fixtures for the Followed traders tests: one day of two traders, the shapes of followed-traders.md. */
import type { FollowedCapture, FollowedDay, FollowedRecord, FollowedTrade } from './types';

export const T = Date.UTC(2026, 9, 13, 14, 0, 0) / 1000; // 10:00:00 ET, 2026-10-13
export const RECORD: FollowedRecord = { wins: 0, losses: 0, scratches: 0, unscored: 0, open: 0, win_rate: null };
export const EV_IN = '/api/followed-traders/evidence/2026-10-13/frames/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg';
export const EV_OUT = '/api/followed-traders/evidence/2026-10-13/frames/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.jpg';

export function trade(over: Partial<FollowedTrade> = {}): FollowedTrade {
  return {
    id: 'x', trader: 'ALPHA', side: 'long', symbol: 'ABCD', status: 'open',
    entry: { first_price: 2, avg_price: 2, ts: T, since_ts: null, known: true },
    adds: [], left_bar: false, now: null, exit: null, pl: null, held: { min_sec: 600, max_sec: 600 }, result: null,
    evidence: { entry: EV_IN, exit: null }, ...over,
  };
}

export function closed(over: Partial<FollowedTrade> = {}): FollowedTrade {
  return trade({
    status: 'closed', result: 'win', held: { min_sec: 300, max_sec: 300 },
    exit: { state: 'at', price: 2.2, low: null, high: null, from_ts: null, to_ts: T + 300, trade_ts: T + 299,
      source: 'ibkr_trades', why: null },
    pl: { per_share: 0.2, pct: 10 }, evidence: { entry: EV_IN, exit: EV_OUT }, ...over,
  });
}

export function capture(over: Partial<FollowedCapture> = {}): FollowedCapture {
  return {
    live: true, clock: '10:09:54', updated_at: T + 600, age_sec: 2, bar_visible: true, title: 'Morning show',
    traders: ['ALPHA', 'BRAVO'], problem: null, problem_at: null,
    bar: [
      { trader: 'ALPHA', image: '/api/followed-traders/live/ALPHA.jpg',
        positions: [{ side: 'long', symbol: 'ABCD', price: 2 }] },
      { trader: 'BRAVO', image: null, positions: [] },
    ],
    ...over,
  };
}

export function day(over: Partial<FollowedDay> = {}): FollowedDay {
  return {
    schema_version: 1, generated_at: T + 602, feed: { state: 'ok', error: null },
    date: '2026-10-13', today: '2026-10-13', dates: ['2026-10-13', '2026-10-09'], capture: capture(),
    prices: { state: 'live', why: null },
    overall: { ...RECORD, wins: 1, open: 1, win_rate: 100 },
    traders: [
      {
        name: 'ALPHA', face: '/api/followed-traders/faces/2026-10-13/ALPHA.jpg',
        record: { ...RECORD, wins: 1, open: 1, win_rate: 100 }, seen: null,
        open: [trade({ id: 'o1', now: { state: 'live', price: 2.5, trade_ts: T + 599, why: null },
          pl: { per_share: 0.5, pct: 25 } })],
        closed: [closed({ id: 'c1', symbol: 'EFGH', entry: { first_price: 2, avg_price: 2, ts: T - 600, since_ts: null, known: true } })],
      },
      {
        name: 'BRAVO', face: null, record: { ...RECORD, unscored: 1 }, seen: null,
        open: [],
        closed: [closed({ id: 'c2', trader: 'BRAVO', symbol: 'TQQQ', result: 'unscored', pl: null,
          entry: { first_price: 77.77, avg_price: 77.77, ts: T - 1200, since_ts: null, known: false },
          exit: { state: 'range', price: null, low: 77.1, high: 77.9, from_ts: T - 900, to_ts: T - 60,
            trade_ts: null, source: 'ibkr_trades', why: null },
          held: { min_sec: 300, max_sec: null } })],
      },
    ],
    ...over,
  };
}
