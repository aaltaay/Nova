/**
 * The stock read's GETs (ADR 036): the read itself, polled while the Trader tab shows; the day's
 * decisions, polled while the sheet shows them; the day's setups that ended, polled while the chart
 * draws them and read at once when a lane's drawn state changes; the history, read once per symbol.
 * The sample desk reads nothing live (`unavailable`), and neither does an API from before the routes
 * (404). A failed poll keeps the last good answer on screen and says so in `error`.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { STOCK_READ_DECISIONS_POLL_MS, STOCK_READ_PAST_POLL_MS, STOCK_READ_PATH, STOCK_READ_POLL_MS } from './constants';
import { normalizeHistory } from './historyNormalize';
import { normalizeDecisions, normalizeStockRead } from './normalize';
import { normalizePastSetups, type PastSetups } from './pastSetups';
import type { StockDecisions, StockHistory, StockRead } from './types';

export interface PolledState<T> {
  data: T | null;
  loading: boolean;
  unavailable: boolean;
  error: string | null;
}

interface PollOptions<T> {
  /** Null reads nothing. */
  url: string | null;
  /** A change clears the last answer (another symbol); a url change alone keeps it on screen. */
  resetKey: string;
  normalize: (raw: unknown) => T | null;
  /** Null reads once. */
  pollMs: number | null;
  active: boolean;
  what: string;
  accept?: (data: T) => boolean;
  /** A change reads at once (and restarts the poll): what the answer depends on moved. */
  nudge?: string;
}

export function usePolledRead<T>({ url, resetKey, normalize, pollMs, active, what, accept, nudge }: PollOptions<T>): PolledState<T> {
  const sample = useSampleDataOptional();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const normalizeRef = useRef(normalize);
  normalizeRef.current = normalize;
  const acceptRef = useRef(accept);
  acceptRef.current = accept;

  useEffect(() => {
    setData(null);
    setUnavailable(false);
    setError(null);
  }, [resetKey]);

  useEffect(() => {
    if (sample || !url || !active) return;
    let cancelled = false;
    let inFlight = false;
    setLoading(true);

    async function read() {
      if (inFlight || !url) return;
      inFlight = true;
      try {
        const res = await fetch(`${API_BASE_URL}${url}`);
        if (res.status === 404) {
          if (!cancelled) setUnavailable(true); // an API from before ADR 036
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = normalizeRef.current(await res.json());
        if (!body) throw new Error(`not a ${what}`);
        if (cancelled || (acceptRef.current && !acceptRef.current(body))) return;
        setData(body);
        setUnavailable(false);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(`The ${what} failed: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    }

    void read();
    const id = pollMs ? window.setInterval(() => void read(), pollMs) : null;
    return () => {
      cancelled = true;
      if (id !== null) window.clearInterval(id);
    };
  }, [sample, url, active, pollMs, what, nudge]);

  // One object per answer, so a Trader tab's ticks do not redraw every consumer.
  return useMemo(
    () => (sample ? SAMPLE_STATE : { data, loading, unavailable, error }),
    [sample, data, loading, unavailable, error],
  ) as PolledState<T>;
}

const SAMPLE_STATE: PolledState<never> = { data: null, loading: false, unavailable: true, error: null };

function symbolPath(symbol: string): string {
  return `${STOCK_READ_PATH}/${encodeURIComponent(symbol)}`;
}

/** Query string for the operator's own plan; empty when there is none. A hand short adds `side=short`. */
export function planQuery(entry: number | null, stop: number | null, side: 'long' | 'short' = 'long'): string {
  if (entry === null || !(entry > 0)) return '';
  const q = new URLSearchParams({ entry: String(entry) });
  if (stop !== null && stop > 0) q.set('stop', String(stop));
  if (side === 'short') q.set('side', 'short');
  return `?${q.toString()}`;
}

/** The read's whole query: the operator's own plan and the position held (`held_*`). */
export function readQuery(entry: number | null, stop: number | null, held = '', side: 'long' | 'short' = 'long'): string {
  const qs = [planQuery(entry, stop, side).replace(/^\?/, ''), held].filter(Boolean).join('&');
  return qs ? `?${qs}` : '';
}

export function useStockRead(
  symbol: string,
  opts: { active: boolean; entry: number | null; stop: number | null; side?: 'long' | 'short'; held?: string;
    /** A change reads at once: on a Sim replay, where the playhead is (ADR 052). */
    nudge?: string },
): PolledState<StockRead> {
  const sym = symbol.trim().toUpperCase();
  return usePolledRead({
    url: sym ? `${symbolPath(sym)}${readQuery(opts.entry, opts.stop, opts.held, opts.side)}` : null,
    resetKey: sym,
    normalize: normalizeStockRead,
    pollMs: STOCK_READ_POLL_MS,
    active: opts.active,
    what: 'stock read',
    accept: r => r.symbol === sym,
    nudge: opts.nudge,
  });
}

export function useStockReadDecisions(symbol: string, active: boolean): PolledState<StockDecisions> {
  const sym = symbol.trim().toUpperCase();
  return usePolledRead({
    url: sym ? `${symbolPath(sym)}/decisions` : null,
    resetKey: sym,
    normalize: normalizeDecisions,
    pollMs: STOCK_READ_DECISIONS_POLL_MS,
    active,
    what: 'decisions read',
    accept: d => d.symbol === sym,
  });
}

/** The day's setups that ended (ADR 036 amendment); `nudge` is the lanes' drawn states, so a setup that
 * fails or ends is read again at once. `tf` 5m: the 5-minute lanes' (the 5-minute chart's). */
export function useStockReadPast(symbol: string, active: boolean, nudge: string,
  tf: '1m' | '5m' = '1m'): PolledState<PastSetups> {
  const sym = symbol.trim().toUpperCase();
  return usePolledRead({
    url: sym ? `${symbolPath(sym)}/past-setups${tf === '5m' ? '?tf=5m' : ''}` : null,
    resetKey: `${sym}:${tf}`,
    normalize: normalizePastSetups,
    pollMs: STOCK_READ_PAST_POLL_MS,
    active,
    what: 'past setups read',
    accept: p => p.symbol === sym,
    nudge,
  });
}

export function useStockReadHistory(symbol: string, active: boolean): PolledState<StockHistory> {
  const sym = symbol.trim().toUpperCase();
  return usePolledRead({
    url: sym ? `${symbolPath(sym)}/history` : null,
    resetKey: sym,
    normalize: normalizeHistory,
    pollMs: null,
    active,
    what: 'history read',
    accept: h => h.symbol === sym,
  });
}
