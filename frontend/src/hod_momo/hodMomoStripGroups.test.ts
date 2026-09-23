import { describe, expect, it } from 'vitest';
import { hodMomoStripGroupWindowSec } from './hodMomoStripConstants';
import { groupIsNew, groupStripAlerts, sameGroup, stripCardPosition } from './hodMomoStripGroups';
import { gateValuesOf, stripAlertsForMode } from './hodMomoStripRows';
import { alertIdentity } from './hodMomoWire';
import type { AlertObject } from './types';

const T0 = Date.parse('2026-09-23T15:02:05Z') / 1000;

function alert(over: Partial<AlertObject> & { id: string }): AlertObject {
  return {
    timestamp: '2026-09-23T15:02:05Z',
    ticker: 'MSS',
    strategy_id: 7,
    strategy_name: 'Low Float - High Rel Vol',
    price: 2.73,
    change_pct: 59.0,
    rvol: 31.5,
    rvol_5min: 167.4,
    float_shares: 300_100,
    gap_pct: null,
    volume: 51_900_000,
    momentum_pct: null,
    rvol_source: 'yfinance',
    consolidation_count: 22,
    consolidated_ids: [],
    consolidation_span_sec: 5,
    created_ts: T0,
    ...over,
  };
}

const S5 = { strategy_id: 5, strategy_name: 'Low Float Volatility Hunter' };
const S7 = { strategy_id: 7, strategy_name: 'Low Float - High Rel Vol' };
const S10 = { strategy_id: 10, strategy_name: 'Squeeze Alert - Up 10% in 10min' };
const S11 = { strategy_id: 11, strategy_name: 'Squeeze Alert - Up 5% in 5min' };

/** The operator's screenshot: MSS fired four strategies at 11:02:05 and again at 11:01:59. */
const SCREENSHOT: AlertObject[] = [
  alert({ id: 'a7', ...S7 }),
  alert({ id: 'a10', ...S10, momentum_pct: 34.5 }),
  alert({ id: 'a11', ...S11, momentum_pct: 31.9 }),
  alert({ id: 'a5', ...S5 }),
  alert({ id: 'b5', ...S5, created_ts: T0 - 6 }),
  alert({ id: 'b7', ...S7, created_ts: T0 - 6 }),
  alert({ id: 'b10', ...S10, created_ts: T0 - 6, momentum_pct: 34.5 }),
  alert({ id: 'b11', ...S11, created_ts: T0 - 6, momentum_pct: 31.9 }),
  alert({ id: 'c10', ticker: 'NNNN', ...S10, created_ts: T0 - 108, price: 6.83 }),
  alert({ id: 'c11', ticker: 'NNNN', ...S11, created_ts: T0 - 108, price: 6.83 }),
];

const WINDOW = hodMomoStripGroupWindowSec(10);

describe('groupStripAlerts', () => {
  it('folds one ticker\'s strategies that fired together into one row; a re-fire starts the next', () => {
    const groups = groupStripAlerts(stripAlertsForMode(SCREENSHOT, 'hod_momo', null), WINDOW);
    expect(groups.map((g) => [g.ticker, g.members.map((m) => m.strategy_id)])).toEqual([
      ['MSS', [5, 7, 10, 11]],
      ['MSS', [5, 7, 10, 11]],
      ['NNNN', [10, 11]],
    ]);
    expect(groups[0].lead.id).toBe('a7');
    expect(groups[1].members.every((m) => m.id.startsWith('b'))).toBe(true);
  });

  it('keeps a lone alert as its own row', () => {
    const groups = groupStripAlerts([alert({ id: 'x' })], WINDOW);
    expect(groups).toHaveLength(1);
    expect(groups[0].members).toHaveLength(1);
    expect(groups[0].key).toBe(alertIdentity(groups[0].lead));
  });

  it('never groups across tickers, or past the window from the oldest member', () => {
    const groups = groupStripAlerts([
      alert({ id: 'late', ...S10, created_ts: T0 + WINDOW + 1 }),
      alert({ id: 'other', ticker: 'NNNN', ...S11, created_ts: T0 + 1 }),
      alert({ id: 'first', ...S7, created_ts: T0 }),
    ], WINDOW);
    expect(groups.map((g) => g.members.map((m) => m.id))).toEqual([['late'], ['other'], ['first']]);
  });

  it('joins interleaved alerts of one ticker and keeps the newest on top', () => {
    const groups = groupStripAlerts([
      alert({ id: 'mss10', ...S10, created_ts: T0 + 2 }),
      alert({ id: 'abc', ticker: 'ABC', created_ts: T0 + 1 }),
      alert({ id: 'mss7', ...S7, created_ts: T0 }),
    ], WINDOW);
    expect(groups.map((g) => g.ticker)).toEqual(['MSS', 'ABC']);
    expect(groups[0].lead.id).toBe('mss10');
  });

  it('keys a row on its oldest member so an arriving strategy never re-keys it', () => {
    const before = groupStripAlerts([alert({ id: 'mss7', ...S7 })], WINDOW);
    const after = groupStripAlerts([
      alert({ id: 'mss10', ...S10, created_ts: T0 + 3 }),
      alert({ id: 'mss7', ...S7 }),
    ], WINDOW);
    expect(after).toHaveLength(1);
    expect(after[0].key).toBe(before[0].key);
    expect(after[0].lead.id).toBe('mss10');
  });

  it('flags the row NEW while any member is new', () => {
    const [group] = groupStripAlerts(SCREENSHOT.slice(0, 4), WINDOW);
    expect(groupIsNew(group, new Set([alertIdentity(SCREENSHOT[2])]))).toBe(true);
    expect(groupIsNew(group, new Set())).toBe(false);
  });

  it('treats a recomputed group with the same members as unchanged', () => {
    const a = groupStripAlerts(SCREENSHOT, WINDOW);
    const b = groupStripAlerts(SCREENSHOT, WINDOW);
    expect(a[0]).not.toBe(b[0]);
    expect(sameGroup(a[0], b[0])).toBe(true);
    expect(sameGroup(a[0], a[1])).toBe(false);
  });
});

describe('gateValuesOf a group', () => {
  it('shows shared values once and the range where strategies measured differently', () => {
    const byKey = Object.fromEntries(gateValuesOf(SCREENSHOT.slice(0, 4)).map((v) => [v.key, v.value]));
    expect(byKey.change_pct).toBe('+59.0%');
    expect(byKey.rvol).toBe('31.5×');
    expect(byKey.float_shares).toBe('300.1K');
    expect(byKey.gap_pct).toBe('—');
    expect(byKey.momentum_pct).toBe('+31.9%–+34.5%');
  });
});

describe('hodMomoStripGroupWindowSec', () => {
  it('is the configured consolidation window plus the flush tick, with a fallback', () => {
    expect(hodMomoStripGroupWindowSec(5)).toBe(6);
    expect(hodMomoStripGroupWindowSec(0)).toBe(11);
    expect(hodMomoStripGroupWindowSec(undefined)).toBe(11);
  });
});

describe('stripCardPosition', () => {
  const viewport = { width: 1000, height: 800 };
  const card = { width: 300, height: 120 };

  it('opens below the bubble when there is room', () => {
    expect(stripCardPosition({ left: 100, top: 40, bottom: 56 }, card, viewport)).toEqual({ left: 100, top: 60 });
  });

  it('flips above near the bottom and stays inside the right edge', () => {
    const pos = stripCardPosition({ left: 900, top: 740, bottom: 756 }, card, viewport);
    expect(pos.top).toBe(740 - 4 - 120);
    expect(pos.left).toBe(1000 - 8 - 300);
  });
});
