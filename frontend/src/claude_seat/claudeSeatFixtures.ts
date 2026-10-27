/** Claude's seat as the backend answers it, for the tests (the approved design's SMPL example). */
import type { ClaudeSeatStatus } from './types';

/** 2026-10-07 09:41 ET, a Wednesday. */
export const SEAT_NOW = 1_791_380_460;

export function seatStatus(over: Partial<ClaudeSeatStatus> = {}): ClaudeSeatStatus {
  return {
    state: 'buy_set',
    text: 'Claude · Buy set SMPL 4.39',
    on: true,
    since: SEAT_NOW - 600,
    beat_at: SEAT_NOW - 40,
    lease_until: SEAT_NOW + 560,
    lapsed: false,
    yielded: false,
    symbol: 'SMPL',
    line: { symbol: 'SMPL', depth: true, tape: true, why_not: null, desk_lines: ['SPIK', 'FLTX'], desk_cap: 2,
      all_lines: ['FLTX', 'SMPL', 'SPIK'], from_tab: null, taken_back: [] },
    positions: [],
    working: [],
    breaks: [{
      id: 'b1', symbol: 'SMPL', qty: 510, trigger: 4.39, top: 4.41, stop: 4.12, target: 4.49, target2: 4.93,
      target1_qty: 250, expires_at: SEAT_NOW + 1800, created_at: SEAT_NOW - 20, why: 'over the 4.38 high',
    }],
    reflexes: [{
      id: 'r1', symbol: 'SMPL', kind: 'bid_pulled', action: 'sell_all', why: null,
      text: 'Sell everything if the 4.30 bid drops under 5,000 shares', expires_at: null,
    }],
    today: { entries: 0, max_entries: 3, pnl: 0, day_stop: -500, fills: 0 },
    limits: { max_shares: 1000, max_risk_usd: 150 },
    note: { text: 'SMPL +54% on news: 31.2M traded on a 4.2M float.', at: SEAT_NOW - 20 },
    events: [
      { at: SEAT_NOW - 20, kind: 'break_set', text: 'set buy 510 SMPL on a print at 4.39 (up to 4.41), stop 4.12' },
      { at: SEAT_NOW - 200, kind: 'watch', text: 'watching SMPL' },
    ],
    read_error: null,
    generated_at: SEAT_NOW,
    ...over,
  };
}
