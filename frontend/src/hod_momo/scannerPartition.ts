/**
 * Partition the shared HOD Momo WS feed into Warrior-style sibling scanners:
 * Small Cap HOD Momentum vs Running Up (strategy 12).
 */
import {
  HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
  HOD_MOMO_RUNNING_UP_STRATEGY_ID,
  STRATEGY_META,
  type StrategyMeta,
} from '../constants';
import type { AlertObject } from './types';

export function isRunningUpStrategy(strategyId: number): boolean {
  return strategyId === HOD_MOMO_RUNNING_UP_STRATEGY_ID;
}

/** HOD Momentum tab strategies — excludes Running Up (sibling scanner). */
export const HOD_MOMENTUM_STRATEGY_META: StrategyMeta[] = STRATEGY_META.filter(
  s => s.id !== HOD_MOMO_RUNNING_UP_STRATEGY_ID,
);

/** Default HOD chip visibility — Former stays off; Running Up lives on its own tab. */
export function defaultHodMomentumVisibleStrategies(): Set<number> {
  return new Set(
    HOD_MOMENTUM_STRATEGY_META.map(s => s.id).filter(
      id => id !== HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
    ),
  );
}

export function partitionScannerAlerts(alerts: AlertObject[]): {
  hodMomentum: AlertObject[];
  runningUp: AlertObject[];
} {
  const hodMomentum: AlertObject[] = [];
  const runningUp: AlertObject[] = [];
  for (const a of alerts) {
    if (isRunningUpStrategy(a.strategy_id)) runningUp.push(a);
    else hodMomentum.push(a);
  }
  return { hodMomentum, runningUp };
}
