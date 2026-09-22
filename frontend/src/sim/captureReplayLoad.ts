/**
 * The one way the desk loads a Session Record into Sim replay, shared by the
 * Sim bar's Day / Ticker pickers and the Records page (QA 2026-09-22, V20:
 * loading a recording lives on Records too). `POST /api/sim/replay` answers
 * the whole clock; an older backend answered the replay fields alone, which
 * blanked the clock (--:--:--) and parked the thumb at the open until the next
 * poll (C42) -- so the reply is folded over the clock the desk already holds,
 * and a reply without the clock makes the clock re-read at once.
 */
import { historicalStatus } from './historicalStatusStore';
import { cancelPendingSimSeek } from './simClockEvents';
import { simClockResource } from './simClockResource';
import type { SimClockState } from './simClockTypes';

type ReplayRequest = <T>(key: string, path: string, body?: unknown, failure?: string) => Promise<T | undefined>;

export const CAPTURE_REPLAY_FAILURE = 'Could not select capture replay; selection was not confirmed';

/** Publish a replay reply on the shared clock; `complete` says whether it carried the clock itself. */
export function publishReplayReply(payload: SimClockState): { clock: SimClockState; complete: boolean } {
  const complete = typeof payload.sim_time_et === 'string';
  const merged = { ...(simClockResource.getSnapshot().data ?? {}), ...payload } as SimClockState;
  if (complete) {
    simClockResource.suspend();
    simClockResource.setData(merged);
  } else {
    simClockResource.invalidate(merged);
  }
  // A capture replaces any historical selection.
  const status = historicalStatus.getSnapshot().data;
  historicalStatus.invalidate({ ...status, jobs: status?.jobs ?? [], selection: null });
  return { clock: simClockResource.getSnapshot().data ?? merged, complete };
}

/** Select `date` / `symbol` (both empty unloads). Undefined when the request failed. */
export async function selectCaptureReplay(
  request: ReplayRequest,
  date: string,
  symbol: string,
): Promise<{ clock: SimClockState; complete: boolean } | undefined> {
  cancelPendingSimSeek();
  simClockResource.suspend();
  try {
    const body = date && symbol ? { date, symbol: symbol.trim().toUpperCase() } : { date: null, symbol: null };
    const payload = await request<SimClockState>('replay', '/replay', body, CAPTURE_REPLAY_FAILURE);
    return payload ? publishReplayReply(payload) : undefined;
  } finally {
    simClockResource.resume();
  }
}
