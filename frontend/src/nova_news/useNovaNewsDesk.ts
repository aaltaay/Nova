/** Fetches the Nova News desk. Metadata only -- no IBKR scanner lease. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL, SCANNER_FETCH_TIMEOUT_MS } from '../constants';
import type { NovaNewsDesk } from '../types/novaNews';
import { NOVA_NEWS_POLL_MS } from './constants';

export function useNovaNewsDesk(enabled: boolean) {
  const [desk, setDesk] = useState<NovaNewsDesk | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const fetchDesk = useCallback(async () => {
    if (!enabled || inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const signal = AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS);
      const res = await fetch(`${API_URL}/news/desk`, { signal });
      if (!res.ok) {
        setFetchError(`Nova News request failed (HTTP ${res.status})`);
        return;
      }
      const data: NovaNewsDesk = await res.json();
      setDesk(data);
      setFetchError(null);
    } catch {
      setFetchError('Nova News request failed -- backend unreachable.');
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    fetchDesk();
    const id = setInterval(fetchDesk, NOVA_NEWS_POLL_MS);
    return () => clearInterval(id);
  }, [enabled, fetchDesk]);

  return { desk, loading, fetchError };
}
