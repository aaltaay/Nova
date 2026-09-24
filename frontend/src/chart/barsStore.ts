/**
 * Shared in-memory OHLCV bar store for chart panes.
 * Dedupes in-flight fetches per (symbol, timeframe). HTTP /bars is store-first
 * on the server (ADR 012); no client serial queue and no 25s abort.
 */
import { API_BASE_URL, CHART_TIMEFRAME_BAR_LIMITS } from '../constants';
import type { RawBar } from '../tickerChartData';
import { getIbkrStatusSnapshot } from '../ibkr/ibkrStatusPoller';

const API_URL = `${API_BASE_URL}/api`;

export type BarsStoreKey = string;

export interface BarsCoverage {
  asOf: string | null;
  completeThrough: string | null;
  filling: boolean;
  derivedFrom?: string | null;
  replay?: boolean;
  replayMode?: string | null;
  /**
   * The pair's last IBKR historical fetch failed (a timeout, an error answer)
   * and nothing has succeeded since (#555): the backend's reason and when it
   * happened (epoch seconds). Absent when the backend states no failure.
   */
  lastError?: string;
  lastErrorTs?: number | null;
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
const generations = new Map<BarsStoreKey, number>();
/** Store-owned controllers: a consumer abort never cancels another chart. */
const controllers = new Map<BarsStoreKey, AbortController>();

export function barsStoreKey(symbol: string, timeframe: string): BarsStoreKey {
  return `${symbol.trim().toUpperCase()}|${timeframe}`;
}

export function clearBarsStoreForTests(): void {
  controllers.forEach(controller => controller.abort());
  controllers.clear();
  entries.clear();
  listeners.clear();
  inflight.clear();
  generations.clear();
}

/** Drop cached bars so the next ensureBars hits the network (Sim scrub). */
export function invalidateBars(symbol: string, timeframe: string): void {
  const key = barsStoreKey(symbol, timeframe);
  entries.delete(key);
  generations.set(key, (generations.get(key) ?? 0) + 1);
  controllers.get(key)?.abort();
  controllers.delete(key);
  inflight.delete(key);
  listeners.get(key)?.forEach(l => l());
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
    ...(cov.replay ? {
      replay: true,
      replayMode: typeof cov.replay_mode === 'string' ? cov.replay_mode : null,
    } : {}),
    ...(typeof cov.last_error === 'string' && cov.last_error ? {
      lastError: cov.last_error,
      lastErrorTs: typeof cov.last_error_ts === 'number' && Number.isFinite(cov.last_error_ts)
        ? cov.last_error_ts
        : null,
    } : {}),
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
  // Replay HTTP owns candles. A broker patch must not replace them.
  if (!coverage?.replay && (getIbkrStatusSnapshot().mode === 'sim' || prev?.coverage?.replay)) {
    return prev ?? { bars: [], revision: 0, fetchedAt: 0 };
  }
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

/**
 * A `bars_patch` pushed when a historical fill lands (`/ws/ticker`). An empty
 * patch never replaces bars the pane already holds -- the same rule as an
 * empty `/bars` answer (ADR 012): a fill that found nothing is no reason to
 * wipe a painted chart.
 */
export function applyBarsPatch(
  symbol: string,
  timeframe: string,
  bars: RawBar[],
  coverage?: BarsCoverage,
): void {
  const current = getBarsEntry(symbol, timeframe);
  if (!coverage?.replay && bars.length === 0 && current && current.bars.length > 0) return;
  setBars(symbol, timeframe, bars, coverage);
}

/**
 * `setsPrice: false` is a print reported for volume only (odd lot, average
 * price, derivatively priced ...): Time & Sales lists it, no candle takes it --
 * its price can sit dollars from the market (backend `sale_conditions.py`).
 */
export function upsertTapePrint10SecBar(
  symbol: string,
  print: { time: string; price: number; size: number; setsPrice?: boolean },
): boolean {
  const sym = symbol.trim().toUpperCase();
  if (print.setsPrice === false) return false;
  if (getIbkrStatusSnapshot().mode === 'sim' || getBarsEntry(sym, '10Sec')?.coverage?.replay) {
    return false;
  }
  const stamp = new Date(print.time).getTime();
  const price = Number(print.price);
  const size = Math.max(0, Number(print.size) || 0);
  if (!sym || !Number.isFinite(stamp) || !Number.isFinite(price) || price <= 0) {
    return false;
  }

  const bucketMs = Math.floor(stamp / 10_000) * 10_000;
  const bucketIso = new Date(bucketMs).toISOString();
  const current = getBarsEntry(sym, '10Sec');
  const bars = [...(current?.bars ?? [])];
  const last = bars.at(-1);

  if (last) {
    const lastMs = new Date(last.t).getTime();
    if (!Number.isFinite(lastMs) || bucketMs < lastMs) return false;
    if (bucketMs === lastMs) {
      bars[bars.length - 1] = {
        ...last,
        h: Math.max(last.h, price),
        l: Math.min(last.l, price),
        c: price,
        v: last.v + size,
      };
    } else {
      bars.push({ t: bucketIso, o: price, h: price, l: price, c: price, v: size });
    }
  } else {
    bars.push({ t: bucketIso, o: price, h: price, l: price, c: price, v: size });
  }

  const limit = CHART_TIMEFRAME_BAR_LIMITS['10Sec'];
  setBars(
    sym,
    '10Sec',
    limit && bars.length > limit ? bars.slice(-limit) : bars,
    current?.coverage ?? {
      asOf: bucketIso,
      completeThrough: null,
      filling: true,
    },
  );
  return true;
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
  signal: AbortSignal,
  limit?: number,
): Promise<RawBar[]> {
  const key = barsStoreKey(symbol, timeframe);
  const generation = generations.get(key) ?? 0;
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
  const data = (await res.json()) as { bars?: RawBar[]; coverage?: unknown };
  if (signal.aborted || (generations.get(key) ?? 0) !== generation) {
    throw new DOMException('Replay position changed', 'AbortError');
  }
  const coverage = parseBarsCoverage(data.coverage);
  if (getIbkrStatusSnapshot().mode === 'sim' && !coverage?.replay) {
    throw new DOMException('Desk mode changed', 'AbortError');
  }
  const bars = data.bars ?? [];
  const current = getBarsEntry(symbol, timeframe);
  if (!coverage?.replay && bars.length === 0 && current && current.bars.length > 0) {
    return current.bars;
  }
  setBars(symbol, timeframe, bars, coverage);
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

  const controller = new AbortController();
  controllers.set(key, controller);
  const promise = fetchSingleBars(sym, timeframe, controller.signal, limit).finally(() => {
    if (inflight.get(key) === promise) inflight.delete(key);
    if (controllers.get(key) === controller) controllers.delete(key);
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
