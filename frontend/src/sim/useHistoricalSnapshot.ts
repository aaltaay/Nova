import { useCallback, useSyncExternalStore } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { matchesSimClockScrub, SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';
import { SIM_HISTORY_POLL_MS } from './simConstants';
import { replayPollResource } from './replayPollResource';
import type { HistoricalDepthBook, HistoricalSelection } from './historicalTypes';

export interface HistoricalSnapshot {
  active: boolean; symbol: string; last: number | null; volume: number | null;
  source: string; as_of: string; error?: string;
  /** True only when a recorded book covers this playhead second (#309). */
  depth_available?: boolean;
  /** That book, or null/undefined when depth was not recorded for this moment. */
  depth?: HistoricalDepthBook | null;
  /** Session open/high/low from reached reported prints (or reached candles). */
  open?: number | null; high?: number | null; low?: number | null;
  /** Close of the last daily bar before the session date. */
  prev_close?: number | null;
  selection?: HistoricalSelection;
  /** The playhead's own second is downloaded; false in a gap or past the edge. */
  covered?: boolean;
  /** Prints whose side the local L2 recording decided (AGENTS.md §3). */
  sides_recorded?: number;
  prints: {
    ordinal?: number; time: string; price: number; size: number; exchange: string;
    conditions?: string; unreported?: boolean;
    /** Real side from a recorded book that held across the print's second; else null. */
    side?: 'ask' | 'bid' | 'between' | null;
    bid?: number | null; ask?: number | null;
    side_source?: string | null;
  }[];
}

function blank(symbol: string): HistoricalSnapshot {
  return { active: true, symbol, last: null, volume: null, source: 'loading', as_of: '', prints: [] };
}
const resources = new Map<string, ReturnType<typeof createResource>>();
function createResource(symbol: string) {
  const poller = replayPollResource<HistoricalSnapshot>(`/history/snapshot/${encodeURIComponent(symbol)}`, () => SIM_HISTORY_POLL_MS);
  let count = 0;
  const seek = (event: Event) => {
    if (matchesSimClockScrub(event, symbol)) poller.invalidate(poller.getSnapshot().data?.active ? blank(symbol) : null);
  };
  const resource = { ...poller, subscribe(listener: () => void) {
    if (++count === 1) window.addEventListener(SIM_CLOCK_SCRUB_EVENT, seek);
    const unsubscribe = poller.subscribe(listener);
    return () => {
      unsubscribe();
      if (--count === 0) {
        window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, seek);
        queueMicrotask(() => { if (!count && resources.get(symbol) === resource) resources.delete(symbol); });
      }
    };
  } };
  return resource;
}
const emptyState = { data: null, error: null };
const noSubscription = () => () => {};
/** Shared single-flight snapshots; seek clears future prints, transient errors retain reached data. */
export function useHistoricalSnapshot(symbol: string, active: boolean) {
  const sim = useIbkrStatus().mode === 'sim';
  const key = symbol.trim().toUpperCase();
  const enabled = sim && active;
  if (enabled && !resources.has(key)) resources.set(key, createResource(key));
  const resource = enabled ? resources.get(key)! : null;
  const subscribe = useCallback((listener: () => void) => resource?.subscribe(listener) ?? noSubscription(), [resource]);
  const state = useSyncExternalStore(subscribe, resource?.getSnapshot ?? (() => emptyState));
  const data = state.data;
  if (!enabled || !data?.active || data.symbol !== key || (data.selection && data.selection.symbol !== key)) return null;
  return state.error ? { ...data, error: state.error } : data;
}
