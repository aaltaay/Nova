/**
 * Shared in-memory OHLCV bar store for chart panes.
 * Dedupes in-flight fetches per (symbol, timeframe). HTTP /bars is store-first
 * on the server (ADR 012); no client serial queue and no 25s abort.
 */
import { API_BASE_URL, CHART_TIMEFRAME_BAR_LIMITS } from '../constants';
import type { RawBar } from '../tickerChartData';

const API_URL = `${API_BASE_URL}/api`;

export type BarsStoreKey = string;

export interface BarsCoverage {
  asOf: string | null;
  completeThrough: string | null;
  filling: boolean;
  derivedFrom?: string | null;
}

export interface BarsStoreEntry {
  bars: RawBar[];
  revision: number;
  fetchedAt: number;
  coverage?: BarsCoverage;
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

export function parseBarsCoverage(raw: unknown): BarsCoverage | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const cov = raw as Record<string, unknown>;
  return {
    asOf: typeof cov.as_of === 'string' ? cov.as_of : null,
    completeThrough: typeof cov.complete_through === 'string' ? cov.complete_through : null,
    filling: Boolean(cov.filling),
    derivedFrom: typeof cov.derived_from === 'string' ? cov.derived_from : null,
  };
}

function notify(key: BarsStoreKey): void {
  const set = listeners.get(key);
  if (!set) return;
  for (const cb of set) cb();
}

export function setBars(
  symbol: string,
  timeframe: string,
  bars: RawBar[],
  coverage?: BarsCoverage,
): BarsStoreEntry {
  const key = barsStoreKey(symbol, timeframe);
  const prev = entries.get(key);
  const next: BarsStoreEntry = {
    bars,
    revision: (prev?.revision ?? 0) + 1,
    fetchedAt: Date.now(),
    coverage,
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
  limit?: number,
): Promise<RawBar[]> {
  const params = new URLSearchParams({ timeframe });
  if (limit != null && limit > 0) params.set('limit', String(limit));
  const res = await fetch(
    `${API_URL}/ticker/${encodeURIComponent(symbol)}/bars?${params.toString()}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`,
    );
  }
  const data = (await res.json()) as { bars?: RawBar[]; coverage?: unknown };
  const bars = data.bars ?? [];
  setBars(symbol, timeframe, bars, parseBarsCoverage(data.coverage));
  return bars;
}

/** Deduped single-TF fetch; writes the store on success. Parallel across timeframes. */
export function ensureBars(
  symbol: string,
  timeframe: string,
  signal?: AbortSignal,
  limit?: number,
): Promise<RawBar[]> {
  const sym = symbol.trim().toUpperCase();
  const key = barsStoreKey(sym, timeframe);
  if (signal?.aborted) {
    return Promise.reject(new DOMException('Aborted', 'AbortError'));
  }
  const existing = inflight.get(key);
  if (existing) {
    if (!signal) return existing;
    return existing.then((bars) => {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      return bars;
    });
  }

  const promise = fetchSingleBars(sym, timeframe, limit).finally(() => {
    if (inflight.get(key) === promise) inflight.delete(key);
  });
  inflight.set(key, promise);
  if (!signal) return promise;
  return promise.then((bars) => {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    return bars;
  });
}

export interface BatchBarsResult {
  results: Record<string, RawBar[]>;
  errors: Record<string, string>;
}

/** Parallel per-TF ensureBars (each /bars is a local store read). */
export async function ensureBarsBatch(
  symbol: string,
  timeframes: string[],
  signal?: AbortSignal,
): Promise<BatchBarsResult> {
  const unique = [...new Set(timeframes.filter(Boolean))];
  if (unique.length === 0) return { results: {}, errors: {} };

  const results: Record<string, RawBar[]> = {};
  const errors: Record<string, string> = {};
  await Promise.all(
    unique.map(async (tf) => {
      if (signal?.aborted) {
        errors[tf] = 'Aborted';
        return;
      }
      try {
        results[tf] = await ensureBars(symbol, tf, signal, CHART_TIMEFRAME_BAR_LIMITS[tf]);
      } catch (err) {
        errors[tf] = err instanceof Error ? err.message : 'Failed to load bars';
      }
    }),
  );
  return { results, errors };
}
