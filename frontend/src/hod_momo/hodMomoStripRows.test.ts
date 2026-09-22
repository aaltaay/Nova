import { describe, expect, it } from 'vitest';
import {
  alertGateValues,
  fmtStripClock,
  fmtStripPrice,
  fmtStripSince,
  gateValuesAllAbsent,
  stripAlertKey,
  stripAlertsForMode,
  stripPrintNote,
} from './hodMomoStripRows';
import { hodMomoStripSinceLabel, hodMomoStripStrategyChip } from './hodMomoStripConstants';
import type { AlertObject } from './types';

function alert(over: Partial<AlertObject> & { id: string }): AlertObject {
  return {
    timestamp: '2026-09-22T12:39:52Z',
    ticker: 'GRML',
    strategy_id: 7,
    strategy_name: 'Low Float - High Rel Vol',
    price: 12.81,
    change_pct: 33.3,
    rvol: 6.4,
    rvol_5min: null,
    float_shares: 8_200_000,
    gap_pct: null,
    volume: 4_820_000,
    momentum_pct: null,
    rvol_source: 'yfinance',
    consolidation_count: 1,
    consolidated_ids: [],
    ...over,
  };
}

describe('hodMomoStripRows', () => {
  it('renders the gate values the alert carries and states the absent ones', () => {
    const values = alertGateValues(alert({ id: 'a' }));
    const byKey = Object.fromEntries(values.map((v) => [v.key, v.value]));
    expect(byKey.change_pct).toBe('+33.3%');
    expect(byKey.rvol).toBe('6.4×');
    expect(byKey.rvol_5min).toBe('—');
    expect(byKey.float_shares).toBe('8.2M');
    expect(byKey.gap_pct).toBe('—');
    expect(byKey.volume).toBe('4.8M');
    expect(byKey.momentum_pct).toBe('—');
    expect(values.map((v) => v.key)).toEqual([
      'change_pct', 'rvol', 'rvol_5min', 'float_shares', 'gap_pct', 'volume', 'momentum_pct',
    ]);
    expect(gateValuesAllAbsent(values)).toBe(false);
  });

  it('never invents a value: an alert with no gate fields is all dashes', () => {
    const values = alertGateValues(alert({
      id: 'b', change_pct: Number.NaN, rvol: null, float_shares: null, volume: null,
    }));
    expect(gateValuesAllAbsent(values)).toBe(true);
  });

  it('partitions by mode and applies the strategy filter to the HOD side only', () => {
    const list = [
      alert({ id: '1', strategy_id: 7 }),
      alert({ id: '2', strategy_id: 12, strategy_name: 'Running Up Alert' }),
      alert({ id: '3', strategy_id: 11 }),
    ];
    expect(stripAlertsForMode(list, 'hod_momo', null).map((a) => a.id)).toEqual(['1', '3']);
    expect(stripAlertsForMode(list, 'hod_momo', new Set([11])).map((a) => a.id)).toEqual(['3']);
    expect(stripAlertsForMode(list, 'running_up', new Set([11])).map((a) => a.id)).toEqual(['2']);
    // A roster mode falls back to the HOD list (the strip has no roster body).
    expect(stripAlertsForMode(list, 'gappers', null).map((a) => a.id)).toEqual(['1', '3']);
  });

  it('keeps the stream order (newest first) and reports "since" as the oldest alert', () => {
    const list = [
      alert({ id: 'new', timestamp: '2026-09-22T12:39:52Z' }),
      alert({ id: 'old', timestamp: '2026-09-22T11:05:00Z' }),
    ];
    expect(stripAlertsForMode(list, 'hod_momo', null)[0].id).toBe('new');
    const since = fmtStripSince(list);
    expect(since).toBe(new Date('2026-09-22T11:05:00Z').toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }));
    expect(fmtStripSince([])).toBeNull();
    expect(hodMomoStripSinceLabel(1, since)).toBe(`1 alert since ${since}`);
    expect(hodMomoStripSinceLabel(3, null)).toBe('3 alerts');
  });

  it('orders newest raised first and drops exact repeats (QA V16)', () => {
    const t = (iso: string) => Date.parse(iso) / 1000;
    const list = [
      alert({ id: 'a', created_ts: t('2026-09-22T03:51:56Z') }),
      // Raised at 03:40 on a print from 23:53 -- used to sit out of order.
      alert({ id: 'stale', timestamp: '2026-09-21T23:53:32Z', created_ts: t('2026-09-22T03:40:53Z') }),
      alert({ id: 'b', created_ts: t('2026-09-22T03:46:28Z') }),
      alert({ id: 'b', created_ts: t('2026-09-22T03:46:28Z') }),
      alert({ id: 'c', created_ts: t('2026-09-22T03:07:04Z') }),
    ];
    expect(stripAlertsForMode(list, 'hod_momo', null).map((a) => a.id)).toEqual(['a', 'b', 'stale', 'c']);
    const stale = list[1];
    expect(fmtStripClock(stale)).toBe(new Date(stale.created_ts! * 1000).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }));
    expect(stripPrintNote(stale)).toMatch(/^print \d{2}:\d{2}:\d{2}, 3h 47m before the alert$/);
    expect(stripPrintNote(alert({ id: 'fresh', created_ts: t('2026-09-22T12:39:55Z') }))).toBeNull();
    // Two alerts that share a legacy id still get distinct React keys.
    expect(stripAlertKey(alert({ id: 'x', created_ts: 1 }))).not.toBe(stripAlertKey(alert({ id: 'x', created_ts: 2 })));
  });

  it('formats clock, price and the strategy chip', () => {
    expect(fmtStripClock(alert({ id: 'x' }))).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    expect(fmtStripClock({ timestamp: '', created_ts: 0 })).toBe('—');
    expect(fmtStripClock({ timestamp: 'bad', created_ts: 1_700_000_000 })).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    expect(fmtStripPrice(12.8)).toBe('12.80');
    expect(fmtStripPrice(null)).toBe('—');
    expect(hodMomoStripStrategyChip(7)).toBe('S7');
  });
});
