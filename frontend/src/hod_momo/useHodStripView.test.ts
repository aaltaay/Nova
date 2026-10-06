/**
 * The one selector both HOD views read (the Scanner's strip and the Trader's
 * Focus rail half): strategy picks, Former Momo, batches, newest first.
 */
import { describe, expect, it } from 'vitest';
import { hodStripGroups } from './useHodStripView';
import type { AlertObject } from './types';

function alert(ticker: string, strategyId: number, raised: number): AlertObject {
  return {
    id: `${raised}-${ticker}-${strategyId}`, timestamp: new Date(raised * 1000).toISOString(), ticker,
    strategy_id: strategyId, strategy_name: `S${strategyId}`, price: 1, change_pct: null, rvol: null, float_shares: null,
    gap_pct: null, volume: null, momentum_pct: null, rvol_source: null, consolidation_count: 1,
    consolidated_ids: [], created_ts: raised,
  };
}

const ALERTS = [
  alert('GRML', 2, 100),
  alert('GRML', 5, 103), // the same batch: one row, two strategies
  alert('ZZZX', 3, 200),
  alert('GRML', 2, 400), // a re-fire: a new row
  alert('RUNR', 12, 500),
];

describe('hodStripGroups', () => {
  it('gives HOD Momo its batches, newest first, under the picked strategies', () => {
    const { groups } = hodStripGroups(ALERTS, 'hod_momo', new Set([2, 3, 5]), 5);
    expect(groups.map((g) => [g.ticker, g.members.map((m) => m.strategy_id)])).toEqual([
      ['GRML', [2]], ['ZZZX', [3]], ['GRML', [2, 5]],
    ]);
    expect(hodStripGroups(ALERTS, 'hod_momo', new Set([3]), 5).groups.map((g) => g.ticker)).toEqual(['ZZZX']);
  });

  it('gives Running Up its own alerts whatever the HOD Momo picks are', () => {
    expect(hodStripGroups(ALERTS, 'running_up', new Set(), 5).groups.map((g) => g.ticker)).toEqual(['RUNR']);
  });
});
