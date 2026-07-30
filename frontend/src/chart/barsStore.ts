/**
 * Shared in-memory OHLCV bar store for chart panes.
 * Dedupes in-flight fetches per (symbol, timeframe) and supports batch warm.
 */
import { API_BASE_URL, CHART_BARS_FETCH_TIMEOUT_MS } from '../constants';
import type { RawBar } from '../tickerChartData';

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
): Promise<RawBar[]> {
  const res = await fetch(
    `${API_URL}/ticker/${encodeURIComponent(symbol)}/bars?timeframe=${encodeURIComponent(timeframe)}`,
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

/** Deduped single-TF fetch; writes the store on success. */
export function ensureBars(
  symbol: string,
  timeframe: string,
  signal?: AbortSignal,
): Promise<RawBar[]> {
  const sym = symbol.trim().toUpperCase();
  const key = barsStoreKey(sym, timeframe);
  const existing = inflight.get(key);
  if (existing) return existing;

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

  const promise = (async () => {
    try {
      const bars = await fetchSingleBars(sym, timeframe, controller.signal);
      setBars(sym, timeframe, bars);
      return bars;
    } finally {
      globalThis.clearTimeout(timeoutId);
      if (signal) signal.removeEventListener('abort', onAbort);
      if (inflight.get(key) === promise) inflight.delete(key);
    }
  })();

  inflight.set(key, promise);
  return promise;
}

export interface BatchBarsResult {
  results: Record<string, RawBar[]>;
  errors: Record<string, string>;
}

/** One HTTP round-trip for multiple timeframes; populates the store per TF. */
export async function ensureBarsBatch(
  symbol: string,
  timeframes: string[],
  signal?: AbortSignal,
): Promise<BatchBarsResult> {
  const sym = symbol.trim().toUpperCase();
  const unique = [...new Set(timeframes.filter(Boolean))];
  if (unique.length === 0) return { results: {}, errors: {} };

  const qs = encodeURIComponent(unique.join(','));
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
    const res = await fetch(
      `${API_URL}/ticker/${encodeURIComponent(sym)}/bars/batch?timeframes=${qs}`,
      { signal: controller.signal },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(
        typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`,
      );
    }
    const data = (await res.json()) as {
      results?: Record<string, { bars?: RawBar[] }>;
      errors?: Record<string, { detail?: string }>;
    };
    const results: Record<string, RawBar[]> = {};
    const errors: Record<string, string> = {};
    for (const tf of unique) {
      const payload = data.results?.[tf];
      if (payload) {
        const bars = payload.bars ?? [];
        setBars(sym, tf, bars);
        results[tf] = bars;
      } else if (data.errors?.[tf]) {
        errors[tf] = String(data.errors[tf].detail ?? 'Failed to load bars');
      }
    }
    return { results, errors };
  } finally {
    globalThis.clearTimeout(timeoutId);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}
