/**
 * The Sim scratch account's clock, for the pages that read its ledger.
 *
 * Sim's practice day is the replay playhead's, not the browser's: the backend
 * keys the Sim ledger's `daily[]` on the playhead (`practice/reference.py`), so
 * a page that took "today" from the wall clock read a replayed Sep 18 as a
 * blank Sep 22 -- "Realized today $0.00" beside the day's real fills, and the
 * calendar outlining the wrong day (QA 2026-09-22, C20 / V32). With nothing
 * loaded off the live edge the scratch account has nothing to trade, which the
 * page should say instead of "No fills in this range" (C69).
 */
import { useCallback, useSyncExternalStore } from 'react';
import { simClockResource } from '../sim/simClockResource';

export interface SimAccountClock {
  /** The playhead, epoch seconds; null off Sim or before the clock is read. */
  nowTs: number | null;
  /** Sim with no replay loaded and not at the live edge (a capture still loading is not "nothing"). */
  nothingLoaded: boolean;
}

const OFF: SimAccountClock = { nowTs: null, nothingLoaded: false };
const noSubscription = () => () => {};

export function useSimAccountClock(sim: boolean): SimAccountClock {
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : noSubscription()),
    [sim],
  );
  const state = useSyncExternalStore(subscribe, simClockResource.getSnapshot);
  const clock = sim ? state.data : null;
  if (!clock) return OFF;
  const playhead = clock.sim_time_et ? Date.parse(clock.sim_time_et) : Number.NaN;
  return {
    nowTs: Number.isFinite(playhead) ? playhead / 1000 : null,
    nothingLoaded: clock.replay_source === 'none' && clock.live_edge !== true && clock.replay_loading !== true,
  };
}
