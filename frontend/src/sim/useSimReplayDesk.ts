/**
 * Is this desk replaying the past right now? (QA W10, 2026-09-22.)
 *
 * On Sim off the live edge "every read is the loaded replay" (AGENTS.md
 * section 3), yet the Trader tab chip and the Focus rail kept printing today's
 * live scanner gap, price and news beside a replay of another day ("GRML
 * +11.0% NEWS" over the replay's "$9.27 +225.29%"). Surfaces that show live
 * scanner values ask this first. True only on the Sim venue, once its clock
 * has answered, while the playhead is off the live edge; at the edge a Sim tab
 * is live and shows the live feed like Paper.
 */
import { useCallback, useSyncExternalStore } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { simClockResource } from './simClockResource';
import type { SimClockState } from './simClockTypes';

/** Pure: a Sim clock off the live edge. Unknown (no clock yet) is not a replay. */
export function isReplayDesk(sim: boolean, clock: SimClockState | null | undefined): boolean {
  return sim && clock != null && clock.live_edge !== true;
}

const noSubscription = () => () => {};

export function useSimReplayDesk(): boolean {
  const sim = useIbkrStatus().mode === 'sim';
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : noSubscription()),
    [sim],
  );
  const clock = useSyncExternalStore(subscribe, simClockResource.getSnapshot).data;
  return isReplayDesk(sim, clock);
}
