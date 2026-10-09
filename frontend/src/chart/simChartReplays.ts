/**
 * Whose candles a Sim pane shows (ADR 020 live-edge amendment).
 *
 * Off the live edge a Sim pane charts the loaded replay, and only the replay:
 * a live answer is discarded and live prints never touch its candles. At the
 * edge a Sim tab is live -- the backend serves the live bars, as it does Paper
 * (`chart_bars.fetch_chart_bars`, `sim.mode.is_replay_desk`) -- and the pane
 * takes them. Reading every Sim tab as a replay threw those live bars away, so
 * each pane at the edge stayed on "Loading…" (operator report 2026-10-09).
 *
 * Until the Sim clock first answers, a Sim pane counts as a replay: it waits
 * for the clock rather than paint live candles over a replay. The answer flips
 * the hook, and the pane fetches again.
 */
import { useCallback, useSyncExternalStore } from 'react';
import { simClockResource } from '../sim';

type LiveEdgeClock = { live_edge?: boolean } | null | undefined;

/** Pure: the replay owns a Sim pane off the live edge, and before the clock answers. */
export function simChartReplays(sim: boolean, clock: LiveEdgeClock): boolean {
  return sim && clock?.live_edge !== true;
}

/** The same rule outside React (the bars store), on the shared Sim clock. */
export function simChartReplaysNow(sim: boolean): boolean {
  return simChartReplays(sim, simClockResource.getSnapshot().data);
}

const noSubscription = () => () => {};
const readLiveEdge = () => simClockResource.getSnapshot().data?.live_edge === true;

/** `sim` is the desk's venue; the answer changes when the playhead reaches or leaves the edge. */
export function useSimChartReplays(sim: boolean): boolean {
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : noSubscription()),
    [sim],
  );
  const liveEdge = useSyncExternalStore(subscribe, readLiveEdge);
  return simChartReplays(sim, liveEdge ? { live_edge: true } : null);
}
