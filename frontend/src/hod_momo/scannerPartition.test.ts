import { describe, expect, it } from 'vitest';
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID } from '../constants';
import type { AlertObject } from './types';
import {
  defaultHodMomentumVisibleStrategies,
  isRunningUpStrategy,
  partitionScannerAlerts,
} from './scannerPartition';

function alert(strategyId: number): AlertObject {
  return {
    id: `a-${strategyId}`,
    timestamp: '2026-07-20T12:00:00Z',
    ticker: 'TEST',
    strategy_id: strategyId,
    strategy_name: 'x',
    price: 1,
    change_pct: 0,
    rvol: 1,
    float_shares: null,
    gap_pct: null,
    volume: 0,
    momentum_pct: null,
    rvol_source: null,
    consolidation_count: 1,
    consolidated_ids: [],
  };
}

describe('scannerPartition', () => {
  it('treats strategy 12 as Running Up', () => {
    expect(isRunningUpStrategy(HOD_MOMO_RUNNING_UP_STRATEGY_ID)).toBe(true);
    expect(isRunningUpStrategy(11)).toBe(false);
  });

  it('splits the shared feed into HOD Momentum vs Running Up', () => {
    const { hodMomentum, runningUp } = partitionScannerAlerts([
      alert(11),
      alert(12),
      alert(7),
    ]);
    expect(hodMomentum.map(a => a.strategy_id)).toEqual([11, 7]);
    expect(runningUp.map(a => a.strategy_id)).toEqual([12]);
  });

  it('defaults HOD visibility without Running Up or Former', () => {
    const ids = defaultHodMomentumVisibleStrategies();
    expect(ids.has(HOD_MOMO_RUNNING_UP_STRATEGY_ID)).toBe(false);
    expect(ids.has(1)).toBe(false);
    expect(ids.has(11)).toBe(true);
  });
});
