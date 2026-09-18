/** Poll GET /api/volume-boost while the tab is mounted. Not a scanner lease. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL, SCANNER_FETCH_TIMEOUT_MS } from '../constants';
import { VOLUME_BOOST_POLL_MS } from './constants';
import type { VolumeBoostView } from './types';

export function useVolumeBoost() {
  const [view, setView] = useState<VolumeBoostView | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const fetchView = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const signal = AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS);
      const res = await fetch(`${API_URL}/volume-boost`, { signal });
      if (!res.ok) {
        setFetchError(`Volume boost request failed (HTTP ${res.status})`);
        return;
      }
      const data: VolumeBoostView = await res.json();
      setView(data);
      setFetchError(null);
    } catch {
      setFetchError('Volume boost request failed -- backend unreachable.');
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchView();
    const id = setInterval(fetchView, VOLUME_BOOST_POLL_MS);
    return () => clearInterval(id);
  }, [fetchView]);

  return { view, loading, fetchError };
}
