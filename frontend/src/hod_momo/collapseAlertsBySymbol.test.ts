import { describe, expect, it } from 'vitest';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import type { AlertObject } from './types';

function alert(
  partial: Partial<AlertObject> & Pick<AlertObject, 'id' | 'ticker' | 'timestamp'>,
): AlertObject {
  return {
    strategy_id: 3,
    strategy_name: 'Low Float - Med Rel Vol',
    price: 1,
    change_pct: 0,
    rvol: 2,
    float_shares: 1e6,
    gap_pct: null,
    volume: 1000,
    momentum_pct: null,
    rvol_source: 'ibkr_pace',
    consolidation_count: 1,
    consolidated_ids: [],
    ...partial,
  };
}

describe('collapseAlertsBySymbol', () => {
  it('keeps one row per ticker and collects distinct strategies', () => {
    const rows = [
      alert({
        id: '1',
        ticker: 'TRT',
        timestamp: '2026-07-14T21:25:55.000Z',
        created_ts: 100,
        strategy_id: 12,
        strategy_name: 'Running Up Alert',
        price: 5.5,
      }),
      alert({
        id: '2',
        ticker: 'AEHR',
        timestamp: '2026-07-14T21:25:54.000Z',
        created_ts: 99,
        strategy_id: 3,
        strategy_name: 'Low Float - Med Rel Vol',
      }),
      alert({
        id: '3',
        ticker: 'TRT',
        timestamp: '2026-07-14T21:25:50.000Z',
        created_ts: 95,
        strategy_id: 3,
        strategy_name: 'Low Float - Med Rel Vol',
        price: 5.1,
      }),
      alert({
        id: '4',
        ticker: 'TRT',
        timestamp: '2026-07-14T21:25:48.000Z',
        created_ts: 93,
        strategy_id: 12,
        strategy_name: 'Running Up Alert',
        price: 5.0,
      }),
    ];
    const out = collapseAlertsBySymbol(rows);
    expect(out).toHaveLength(2);
    expect(out[0].ticker).toBe('TRT');
    expect(out[0].price).toBe(5.5);
    expect(out[0].strategies?.map(s => s.id)).toEqual([12, 3]);
    expect(out[0].consolidation_count).toBe(3);
    expect(out[1].ticker).toBe('AEHR');
    expect(out[1].strategies?.map(s => s.id)).toEqual([3]);
  });

  it('does not inflate Warrior burst badge across long gaps', () => {
    const rows = [
      alert({
        id: '1',
        ticker: 'CJMB',
        timestamp: '2026-07-14T21:25:55.000Z',
        created_ts: 3000,
        consolidation_count: 2,
      }),
      alert({
        id: '2',
        ticker: 'CJMB',
        timestamp: '2026-07-14T20:50:00.000Z',
        created_ts: 1000,
        consolidation_count: 50,
        strategy_id: 12,
        strategy_name: 'Running Up Alert',
      }),
    ];
    const out = collapseAlertsBySymbol(rows, 15);
    expect(out).toHaveLength(1);
    expect(out[0].consolidation_count).toBe(2);
    expect(out[0].strategies?.map(s => s.id).sort((a, b) => a - b)).toEqual([3, 12]);
  });

  it('preserves newest-first ticker order', () => {
    const rows = [
      alert({ id: '1', ticker: 'ZZZ', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 100 }),
      alert({ id: '2', ticker: 'AAA', timestamp: '2026-07-14T21:25:54.000Z', created_ts: 99 }),
      alert({ id: '3', ticker: 'ZZZ', timestamp: '2026-07-14T21:25:50.000Z', created_ts: 95 }),
    ];
    expect(collapseAlertsBySymbol(rows).map(r => r.ticker)).toEqual(['ZZZ', 'AAA']);
  });

  it('returns empty input unchanged', () => {
    expect(collapseAlertsBySymbol([])).toEqual([]);
  });
});
