import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { replayPollResource } from './replayPollResource';
import { SIM_HISTORY_IDLE_POLL_MS, SIM_HISTORY_POLL_MS } from './simConstants';
import type { HistoricalStatus } from './historicalTypes';
let openPanels = 0;
export const historicalStatus = replayPollResource<HistoricalStatus>('/history', data =>
  openPanels || (Array.isArray(data?.jobs) && data.jobs.some(job => ['running', 'pause_requested'].includes(job.status)))
    ? SIM_HISTORY_POLL_MS : SIM_HISTORY_IDLE_POLL_MS);
export function useHistoricalStatus(open: boolean) {
  const subscribe = useCallback((listener: () => void) => historicalStatus.subscribe(listener), []);
  const state = useSyncExternalStore(subscribe, historicalStatus.getSnapshot);
  useEffect(() => {
    if (!open) return;
    openPanels++;
    void historicalStatus.refresh();
    return () => { openPanels--; };
  }, [open]);
  return state;
}
