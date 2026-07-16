import { describe, expect, it } from 'vitest';
import { collapseConsecutiveTickerAlerts, incrementalCollapse } from './collapseConsecutiveTickerAlerts';
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

describe('incrementalCollapse', () => {
  it('returns prevCollapsed unchanged when newHead is empty', () => {
    const prev = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 100 }),
    ];
    const result = incrementalCollapse([], prev, 15);
    expect(result).toBe(prev);
  });

  it('returns prevCollapsed by reference for unchanged tail — object identity stable', () => {
    const prev = [
      alert({ id: '2', ticker: 'AEHR', timestamp: '2026-07-14T21:25:54.000Z', created_ts: 100 }),
      alert({ id: '3', ticker: 'MOMO', timestamp: '2026-07-14T21:25:50.000Z', created_ts: 95 }),
    ];
    const newHead = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:58.000Z', created_ts: 104 }),
    ];
    const result = incrementalCollapse(newHead, prev, 15);
    // TRT !== AEHR, so no boundary merge; tail must be the same references
    expect(result[1]).toBe(prev[0]); // AEHR same object
    expect(result[2]).toBe(prev[1]); // MOMO same object
  });

  it('merges boundary items when same ticker within gap', () => {
    const prevItem = alert({ id: '2', ticker: 'TRT', timestamp: '2026-07-14T21:25:53.000Z', created_ts: 98 });
    const prev = [prevItem];
    const newHead = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 100 }),
    ];
    const result = incrementalCollapse(newHead, prev, 15);
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('TRT');
    expect(result[0].consolidation_count).toBe(2);
  });

  it('does not merge boundary items when gap is too large', () => {
    const prev = [
      alert({ id: '2', ticker: 'TRT', timestamp: '2026-07-14T21:20:00.000Z', created_ts: 50 }),
    ];
    const newHead = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 200 }),
    ];
    const result = incrementalCollapse(newHead, prev, 15);
    expect(result).toHaveLength(2);
    expect(result[1]).toBe(prev[0]); // tail item same reference
  });

  it('matches full recompute output for a multi-alert batch', () => {
    // Set up previous list with two items
    const prevAlerts = [
      alert({ id: '3', ticker: 'AEHR', timestamp: '2026-07-14T21:25:50.000Z', created_ts: 95 }),
      alert({ id: '4', ticker: 'MOMO', timestamp: '2026-07-14T21:25:45.000Z', created_ts: 90 }),
    ];
    const prevCollapsed = collapseConsecutiveTickerAlerts(prevAlerts, 15);
    const newHead = [
      alert({ id: '1', ticker: 'TRT', timestamp: '2026-07-14T21:25:58.000Z', created_ts: 104 }),
      alert({ id: '2', ticker: 'TRT', timestamp: '2026-07-14T21:25:56.000Z', created_ts: 102 }),
    ];
    const allAlerts = [...newHead, ...prevAlerts];
    const fullResult = collapseConsecutiveTickerAlerts(allAlerts, 15);
    const incResult = incrementalCollapse(newHead, prevCollapsed, 15);
    // Both should have the same ticker sequence and counts
    expect(incResult.map(r => r.ticker)).toEqual(fullResult.map(r => r.ticker));
    expect(incResult.map(r => r.consolidation_count)).toEqual(fullResult.map(r => r.consolidation_count));
  });
});
