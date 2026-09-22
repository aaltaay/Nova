/**
 * Keeps a replay loaded mid-download current: re-selects the same window as new
 * prints are committed, so the tape grows under the playhead instead of the
 * operator reloading by hand. Mounted once, in the Sim session bar.
 *
 * Quiet on purpose: no sim-clock scrub event. A scrub wipes and refits every
 * chart, which would throw away the operator's zoom every ten seconds; the
 * chart and tape pollers already read whatever selection is current.
 */
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { historicalStatus } from './historicalStatusStore';
import { replayPost, replayRequest } from './replayRequest';
import { shouldRefreshSelection } from './simProgressiveReplay';
import { windowKey } from './simReplayOffer';
import { SIM_HISTORY_REQUEST_FAILED, SIM_PROGRESSIVE_RELOAD_MS } from './simConstants';
import { serializeSimSessionMutation } from './simSessionMutations';
import type { HistoricalSelection } from './historicalTypes';

export function useProgressiveReplay(active: boolean): void {
  const subscribe = useCallback(
    (listener: () => void) => (active ? historicalStatus.subscribe(listener) : () => {}),
    [active],
  );
  const status = useSyncExternalStore(subscribe, historicalStatus.getSnapshot);
  const lastAt = useRef(0);
  const inFlight = useRef(false);
  /** A window whose re-select failed (e.g. grew past the selection cap) is left alone. */
  const refused = useRef<string | null>(null);

  useEffect(() => {
    if (!active || inFlight.current) return;
    const data = status.data;
    const selection = data?.selection;
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    if (!selection || refused.current === windowKey(selection)) return;
    if (!shouldRefreshSelection(selection, jobs, lastAt.current, Date.now(), SIM_PROGRESSIVE_RELOAD_MS)) return;
    inFlight.current = true;
    lastAt.current = Date.now();
    const spec = { symbol: selection.symbol, date: selection.date, start: selection.start, end: selection.end };
    void serializeSimSessionMutation('/history/select', () =>
      replayRequest<HistoricalSelection>('/history/select', replayPost(spec), SIM_HISTORY_REQUEST_FAILED))
      .then(selected => {
        const current = historicalStatus.getSnapshot().data;
        historicalStatus.setData({
          ...current, jobs: Array.isArray(current?.jobs) ? current.jobs : [], selection: selected,
        });
      })
      .catch(error => {
        refused.current = windowKey(spec);
        console.warn('Sim progressive replay: re-select refused; keeping the loaded coverage', error);
      })
      .finally(() => { inFlight.current = false; });
  }, [active, status.data]);
}
