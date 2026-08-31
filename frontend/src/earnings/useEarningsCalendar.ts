/** Fetches the Earnings calendar view (backend/earnings_calendar.py) for one
 * range. `TabModuleHost` only mounts the active tab's panel, so polling starts
 * on mount and stops on unmount for free -- this is a metadata list, not an
 * IBKR scanner lease (single-market-data-feed.mdc), so it has no /ws/scanner
 * price stream and must not be folded into useScannerData.ts. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL, EARNINGS_POLL_MS, SCANNER_FETCH_TIMEOUT_MS } from '../constants';
import type { EarningsRange, EarningsView } from '../types/earnings';

export function useEarningsCalendar(range: EarningsRange) {
  const [view, setView] = useState<EarningsView | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const fetchView = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const signal = AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS);
      const res = await fetch(`${API_URL}/earnings?range=${range}`, { signal });
      if (!res.ok) {
        setFetchError(`Earnings request failed (HTTP ${res.status})`);
        return;
      }
      const data: EarningsView = await res.json();
      setView(data);
      setFetchError(null);
    } catch {
      setFetchError('Earnings request failed -- backend unreachable.');
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    fetchView();
    const id = setInterval(fetchView, EARNINGS_POLL_MS);
    return () => clearInterval(id);
  }, [fetchView]);

  return { view, loading, fetchError };
}
