/**
 * What this tab's replay state is, for every surface that must not pretend.
 *
 * Shared so the prompt strip and the quote rail cannot disagree: both read one
 * clock poll and one pure decision (`simReplayTarget`).
 */
import { useCallback, useSyncExternalStore } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { simClockResource } from './simClockResource';
import { simReplayTarget, type SimReplayTarget } from './simReplayTarget';
import type { SimClockState } from './simClockTypes';

export interface SimReplayTargetState {
  sim: boolean;
  clock: SimClockState | null;
  target: SimReplayTarget;
}

export function useSimReplayTarget(symbol: string): SimReplayTargetState {
  const sim = useIbkrStatus().mode === 'sim';
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : () => {}),
    [sim],
  );
  const state = useSyncExternalStore(subscribe, simClockResource.getSnapshot);
  const clock = sim ? state.data : null;
  return { sim, clock, target: simReplayTarget(symbol, clock, sim) };
}
