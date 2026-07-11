/** Polls GET /api/strategy/watchlist on an interval — same REST-poll pattern as scanner tabs. */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, WATCHLIST_POLL_INTERVAL_MS } from '../constants';
import type { WatchlistEntry } from './types';

const API = `${API_BASE_URL}/api/strategy`;

export interface UseWatchlistReturn {
  entries: WatchlistEntry[];
  loading: boolean;
  error: string | null;
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
        const data = await res.json();
        if (!cancelled) {
          setEntries(data.entries ?? []);
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
