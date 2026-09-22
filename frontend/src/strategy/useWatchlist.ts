/** Polls GET /api/strategy/watchlist on an interval — same REST-poll pattern as scanner tabs. */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, WATCHLIST_POLL_INTERVAL_MS } from '../constants';
import type { WatchlistEntry } from './types';

const API = `${API_BASE_URL}/api/strategy`;
const WATCHLIST_UNREADABLE = 'Watchlist reply was not readable';

export interface UseWatchlistReturn {
  entries: WatchlistEntry[];
  loading: boolean;
  error: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * The entries of a /api/strategy/watchlist reply, each one shaped enough to
 * render (WatchCell reads five_pillars.pillars and composite_score).
 *
 * QA C15: a reply that is a JSON array has `data.entries` ===
 * Array.prototype.entries -- a function -- so `data.entries ?? []` handed React
 * a function, React ran it as a state updater and the whole desk went down.
 * A body that is not an object is an unreadable reply, never a watchlist.
 */
export function readWatchlistEntries(data: unknown): WatchlistEntry[] | null {
  if (!isRecord(data)) return null;
  const raw = data.entries;
  if (!Array.isArray(raw)) return null;
  return raw.filter((entry): entry is WatchlistEntry => {
    if (!isRecord(entry) || typeof entry.symbol !== 'string' || !entry.symbol.trim()) return false;
    if (typeof entry.composite_score !== 'number' || !Number.isFinite(entry.composite_score)) return false;
    const pillars = entry.five_pillars;
    return isRecord(pillars) && Array.isArray(pillars.pillars);
  });
}

export function useWatchlist(enabled: boolean): UseWatchlistReturn {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const res = await fetch(`${API}/watchlist`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const entries = readWatchlistEntries(await res.json());
        if (!entries) throw new Error(WATCHLIST_UNREADABLE);
        if (!cancelled) {
          setEntries(entries);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load watchlist');
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    poll();
    const interval = setInterval(poll, WATCHLIST_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled]);

  return { entries, loading, error };
}
