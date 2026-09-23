/**
 * The Five Pillars for the quote panel's symbol, ranked on the watchlist or
 * not (operator ask, 2026-09-23). A ranked symbol reads its entry from the
 * watchlist poll the desk already runs; any other symbol asks
 * GET /api/strategy/watchlist/{symbol}, which grades its own scanner row or
 * its live quote, polled while the symbol is on screen. The sample desk sends
 * nothing (V4) and shows only its own watchlist.
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { symbolPillarsPath, WATCHLIST_STRIP_POLL_MS } from '../constantGroups/watchlist_strip';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { readWatchlistEntries } from './useWatchlist';
import type { WatchlistEntry } from './types';

export interface SymbolPillars {
  entry: WatchlistEntry | null;
  /** 'watchlist' for a ranked entry; else the board the grade came from, or 'quote'. */
  source: string | null;
  rank: number | null;
  error: string | null;
  loading: boolean;
}

const NONE: SymbolPillars = { entry: null, source: null, rank: null, error: null, loading: false };

/** `{symbol, source, rank, entry}` -> the grade, or null when the body is not one. */
export function readSymbolPillars(body: unknown): Omit<SymbolPillars, 'error' | 'loading'> | null {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  const raw = body as { source?: unknown; rank?: unknown; entry?: unknown };
  const [entry] = readWatchlistEntries({ entries: [raw.entry] }) ?? [];
  if (!entry) return null;
  return {
    entry,
    source: typeof raw.source === 'string' ? raw.source : null,
    rank: typeof raw.rank === 'number' && Number.isFinite(raw.rank) ? raw.rank : null,
  };
}

export function useSymbolPillars(symbol: string | null | undefined, ranked: WatchlistEntry | null, rank: number | null = null): SymbolPillars {
  const sym = (symbol ?? '').trim().toUpperCase();
  const fetchIt = Boolean(sym) && !ranked && !onSampleDesk();
  const [state, setState] = useState<SymbolPillars & { symbol: string }>({ ...NONE, symbol: '' });

  useEffect(() => {
    if (!fetchIt) return undefined;
    let cancelled = false;
    setState(prev => (prev.symbol === sym ? prev : { ...NONE, symbol: sym, loading: true }));
    async function poll() {
      try {
        const res = await novaFetch(`${API_URL}${symbolPillarsPath(sym)}`);
        if (!res.ok) throw new Error(`Five Pillars: HTTP ${res.status}`);
        const read = readSymbolPillars(await res.json());
        if (!read) throw new Error('Five Pillars: unreadable response');
        if (!cancelled) setState({ ...read, error: null, loading: false, symbol: sym });
      } catch (err) {
        if (!cancelled) {
          setState(prev => ({ ...(prev.symbol === sym ? prev : NONE), symbol: sym, loading: false,
            error: err instanceof Error ? err.message : String(err) }));
        }
      }
    }
    void poll();
    const id = window.setInterval(() => void poll(), WATCHLIST_STRIP_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [fetchIt, sym]);

  if (ranked) return { entry: ranked, source: 'watchlist', rank, error: null, loading: false };
  if (!fetchIt || state.symbol !== sym) return { ...NONE, loading: fetchIt };
  return { entry: state.entry, source: state.source, rank: state.rank, error: state.error, loading: state.loading };
}
