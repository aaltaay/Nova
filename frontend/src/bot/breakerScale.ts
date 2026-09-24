/**
 * The loss-breaker bar's arithmetic (ADR 032): where a dollar amount sits on the
 * bar, the dollar amount under the pointer, and the range each marker may move
 * in -- the bounds, the $5 step, and the bot trip always above the all-stop.
 * The backend checks every rule again (`bot/breaker_limits.py`). Pure.
 */
import {
  BOT_BREAKER_HARD_BOUNDS,
  BOT_BREAKER_SOFT_BOUNDS,
  BOT_BREAKER_STEP_USD,
  BOT_HARD_BREAKER_USD,
  BOT_SOFT_BREAKER_USD,
} from '../constantGroups/bot';
import type { BotBreakers } from './types';

export type BreakerKey = 'soft' | 'hard';

/** Round floors the bar may span, tightest first; a bigger loss rounds to the next $1,000. */
const FLOORS = [-250, -500, -1000, -2000, -3000, -5000, -6000];

export interface BreakerLimits {
  soft: number;
  hard: number;
  softBounds: readonly [number, number];
  hardBounds: readonly [number, number];
  step: number;
}

/** The session's breakers, or the fixed pair an API older than ADR 032 keeps. */
export function breakerLimits(b: BotBreakers | undefined): BreakerLimits {
  return {
    soft: b?.soft_usd ?? BOT_SOFT_BREAKER_USD,
    hard: b?.hard_usd ?? BOT_HARD_BREAKER_USD,
    softBounds: (b?.bounds?.soft_usd as [number, number] | undefined) ?? BOT_BREAKER_SOFT_BOUNDS,
    hardBounds: (b?.bounds?.hard_usd as [number, number] | undefined) ?? BOT_BREAKER_HARD_BOUNDS,
    step: b?.bounds?.step_usd ?? BOT_BREAKER_STEP_USD,
  };
}

/** The bar's left end: room past the all-stop and today's loss, on a round number. */
export function breakerFloor(hard: number, dayPnl: number | null): number {
  const need = Math.min(hard * 1.25, dayPnl != null && dayPnl < 0 ? dayPnl * 1.1 : 0);
  const floor = FLOORS.find(f => f <= need);
  return floor ?? Math.floor(need / 1000) * 1000;
}

/** Where `v` sits on the floor .. $0 bar, 0-100 (a gain pins to the right end). */
export function breakerPct(v: number, floor: number): number {
  if (floor >= 0) return 100;
  return Math.max(0, Math.min(100, ((v - floor) / -floor) * 100));
}

/** The range one marker may move in: its bounds, and never past the other marker. */
export function markerRange(key: BreakerKey, lim: BreakerLimits, other: number): [number, number] {
  if (key === 'soft') return [Math.max(lim.softBounds[0], other + lim.step), lim.softBounds[1]];
  return [lim.hardBounds[0], Math.min(lim.hardBounds[1], other - lim.step)];
}

export function snap(v: number, step: number): number {
  return Math.round(v / step) * step;
}

export function clamp(v: number, [lo, hi]: [number, number]): number {
  return Math.max(lo, Math.min(hi, v));
}

/** The dollar amount at `fraction` (0 = the floor, 1 = $0) of the bar, snapped and kept in range. */
export function valueAt(fraction: number, floor: number, step: number, range: [number, number]): number {
  const f = Math.max(0, Math.min(1, fraction));
  return clamp(snap(floor + f * -floor, step), range);
}
