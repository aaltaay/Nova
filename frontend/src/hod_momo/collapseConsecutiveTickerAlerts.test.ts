import { describe, expect, it } from 'vitest';
import { collapseConsecutiveTickerAlerts } from './collapseConsecutiveTickerAlerts';
import type { AlertObject } from './types';

function alert(partial: Partial<AlertObject> & Pick<AlertObject, 'id' | 'ticker' | 'timestamp'>): AlertObject {
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

describe('collapseConsecutiveTickerAlerts', () => {
  it('merges consecutive same ticker within the gap', () => {
    const rows = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 100 }),
      alert({ id: '2', ticker: 'TRT', timestamp: '2026-07-14T21:25:50.000Z', created_ts: 95 }),
      alert({ id: '3', ticker: 'TRT', timestamp: '2026-07-14T21:25:48.000Z', created_ts: 93 }),
    ];
    const out = collapseConsecutiveTickerAlerts(rows, 15);
    expect(out).toHaveLength(1);
    expect(out[0].ticker).toBe('TRT');
    expect(out[0].consolidation_count).toBe(3);
    expect(out[0].consolidation_span_sec).toBeGreaterThanOrEqual(5);
  });

  it('does not merge different tickers', () => {
    const rows = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 100 }),
      alert({ id: '2', ticker: 'AEHR', timestamp: '2026-07-14T21:25:54.000Z', created_ts: 99 }),
    ];
    expect(collapseConsecutiveTickerAlerts(rows, 15)).toHaveLength(2);
  });

  it('starts a new burst when the gap is too large', () => {
    const rows = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 200 }),
      alert({ id: '2', ticker: 'TRT', timestamp: '2026-07-14T21:20:00.000Z', created_ts: 100 }),
    ];
    expect(collapseConsecutiveTickerAlerts(rows, 15)).toHaveLength(2);
  });
});
