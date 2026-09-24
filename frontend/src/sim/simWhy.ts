/**
 * Why a Sim control is locked right now, in the operator's words -- the reason
 * it carries in `data-why` (ux/whyTip.ts). Pure: callers pass the clock and the
 * request keys in flight that they already hold (useReplayActions).
 */
import {
  SIM_WHY_BUSY, SIM_WHY_CLOCK_PENDING, SIM_WHY_NOT_SIM, SIM_WHY_PICK_DAY, simWhyReplayBusy,
} from './simConstants';
import type { SimClockState } from './simClockTypes';

export type SimBusyKey = keyof typeof SIM_WHY_BUSY;

/** No clock yet, or a clock off the Sim venue; null when Sim time can move. */
export function simClockWhy(clock: SimClockState | null | undefined): string | null {
  if (!clock) return SIM_WHY_CLOCK_PENDING;
  return clock.sim ? null : SIM_WHY_NOT_SIM;
}

/** The first of `keys` with a request in flight, in words; null when none is. */
export function simBusyWhy(busy: ReadonlySet<string>, keys: readonly SimBusyKey[]): string | null {
  const key = keys.find(k => busy.has(k));
  return key ? SIM_WHY_BUSY[key] : null;
}

/** A capture load or Close replay in flight (`replay`): `symbol` is the ticker being loaded, '' for a close. */
export function simReplayWhy(busy: ReadonlySet<string>, symbol: string): string | null {
  return busy.has('replay') ? simWhyReplayBusy(symbol) : null;
}

/** The recording Ticker picker: locked while a replay changes, and until a Day is picked. */
export function simTickerWhy(busy: ReadonlySet<string>, day: string, symbol: string): string | null {
  return simReplayWhy(busy, symbol) ?? (day ? null : SIM_WHY_PICK_DAY);
}
