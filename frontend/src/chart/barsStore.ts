/**
 * Shared in-memory OHLCV bar store for chart panes.
 * Dedupes in-flight fetches per (symbol, timeframe) and serializes IBKR historicals.
 */
import {
  API_BASE_URL,
  CHART_BARS_FETCH_TIMEOUT_MS,
  CHART_TIMEFRAME_BAR_LIMITS,
  chartBarsFetchPriority,
} from '../constants';
import type { RawBar } from '../tickerChartData';
import { enqueueBarsFetch, resetBarsFetchQueueForTests } from './barsFetchQueue';

const API_URL = `${API_BASE_URL}/api`;

export type BarsStoreKey = string;

export interface BarsStoreEntry {
  bars: RawBar[];
  revision: number;
  fetchedAt: number;
}

type Listener = () => void;

const entries = new Map<BarsStoreKey, BarsStoreEntry>();
const listeners = new Map<BarsStoreKey, Set<Listener>>();
const inflight = new Map<BarsStoreKey, Promise<RawBar[]>>();

export function barsStoreKey(symbol: string, timeframe: string): BarsStoreKey {
  return `${symbol.trim().toUpperCase()}|${timeframe}`;
}

export function clearBarsStoreForTests(): void {
  entries.clear();
  listeners.clear();
  inflight.clear();
  resetBarsFetchQueueForTests();
}

export function getBarsEntry(symbol: string, timeframe: string): BarsStoreEntry | null {
  return entries.get(barsStoreKey(symbol, timeframe)) ?? null;
}

export function isBarsEntryFresh(entry: BarsStoreEntry | null, maxAgeMs: number): boolean {
  if (!entry) return false;
  return Date.now() - entry.fetchedAt <= maxAgeMs;
}

function notify(key: BarsStoreKey): void {
  const set = listeners.get(key);
  if (!set) return;
  for (const cb of set) cb();
}

export function setBars(symbol: string, timeframe: string, bars: RawBar[]): BarsStoreEntry {
  const key = barsStoreKey(symbol, timeframe);
  const prev = entries.get(key);
  const next: BarsStoreEntry = {
    bars,
    revision: (prev?.revision ?? 0) + 1,
    fetchedAt: Date.now(),
  };
  entries.set(key, next);
  notify(key);
  return next;
}

export function subscribeBars(
  symbol: string,
  timeframe: string,
  listener: Listener,
): () => void {
  const key = barsStoreKey(symbol, timeframe);
  let set = listeners.get(key);
  if (!set) {
    set = new Set();
    listeners.set(key, set);
  }
  set.add(listener);
  return () => {
    set!.delete(listener);
    if (set!.size === 0) listeners.delete(key);
  };
}

async function fetchSingleBars(
  symbol: string,
  timeframe: string,
  signal?: AbortSignal,
  limit?: number,
): Promise<RawBar[]> {
  const params = new URLSearchParams({ timeframe });
  if (limit != null && limit > 0) params.set('limit', String(limit));
  const res = await fetch(
    `${API_URL}/ticker/${encodeURIComponent(symbol)}/bars?${params.toString()}`,
    { signal },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`,
    );
  }
  const data = (await res.json()) as { bars?: RawBar[] };
  return data.bars ?? [];
}

/** Deduped single-TF fetch; writes the store on success. Serialized across timeframes. */
export function ensureBars(
  symbol: string,
  timeframe: string,
  signal?: AbortSignal,
  limit?: number,
): Promise<RawBar[]> {
  const sym = symbol.trim().toUpperCase();
  const key = barsStoreKey(sym, timeframe);
  const existing = inflight.get(key);
  if (existing) return existing;

  let promise!: Promise<RawBar[]>;
  promise = enqueueBarsFetch({
    priority: chartBarsFetchPriority(timeframe),
    signal,
    run: async () => {
      if (signal?.aborted) {
        throw new DOMException('Aborted', 'AbortError');
      }
      const controller = new AbortController();
      const onAbort = () => controller.abort();
      if (signal) {
        if (signal.aborted) controller.abort();
        else signal.addEventListener('abort', onAbort, { once: true });
      }
      const timeoutId = globalThis.setTimeout(
        () => controller.abort(),
        CHART_BARS_FETCH_TIMEOUT_MS,
      );
      try {
        const bars = await fetchSingleBars(sym, timeframe, controller.signal, limit);
        setBars(sym, timeframe, bars);
        return bars;
      } finally {
        globalThis.clearTimeout(timeoutId);
        if (signal) signal.removeEventListener('abort', onAbort);
      }
    },
  }).finally(() => {
    if (inflight.get(key) === promise) inflight.delete(key);
  });

  inflight.set(key, promise);
  return promise;
}

export interface BatchBarsResult {
  results: Record<string, RawBar[]>;
  errors: Record<string, string>;
}

/** Sequential per-TF ensureBars (each gets a full timeout after dequeue). */
export async function ensureBarsBatch(
  symbol: string,
  timeframes: string[],
  signal?: AbortSignal,
): Promise<BatchBarsResult> {
  const sym = symbol.trim().toUpperCase();
  const unique = [...new Set(timeframes.filter(Boolean))];
  if (unique.length === 0) return { results: {}, errors: {} };

  const results: Record<string, RawBar[]> = {};
  const errors: Record<string, string> = {};
  for (const tf of unique) {
    if (signal?.aborted) {
      errors[tf] = 'Aborted';
      continue;
    }
    try {
      results[tf] = await ensureBars(sym, tf, signal, CHART_TIMEFRAME_BAR_LIMITS[tf]);
    } catch (err) {
      errors[tf] = err instanceof Error ? err.message : 'Failed to load bars';
    }
  }
  return { results, errors };
}
