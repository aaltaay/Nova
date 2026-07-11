/** Polls GET /api/journal/metrics + /api/journal/signals on an interval — same REST-poll pattern as useWatchlist. */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, JOURNAL_POLL_INTERVAL_MS, JOURNAL_RECENT_SIGNALS_LIMIT } from '../constants';
import type { JournalMetrics, JournalSignalRow } from './types';

const API = `${API_BASE_URL}/api/journal`;

export interface UseJournalReturn {
  metrics: JournalMetrics | null;
  signals: JournalSignalRow[];
  loading: boolean;
  error: string | null;
}

export function useJournal(enabled: boolean): UseJournalReturn {
  const [metrics, setMetrics] = useState<JournalMetrics | null>(null);
  const [signals, setSignals] = useState<JournalSignalRow[]>([]);
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
        const [metricsRes, signalsRes] = await Promise.all([
          fetch(`${API}/metrics`),
          fetch(`${API}/signals?limit=${JOURNAL_RECENT_SIGNALS_LIMIT}`),
        ]);
        if (!metricsRes.ok) throw new Error(`HTTP ${metricsRes.status}`);
        if (!signalsRes.ok) throw new Error(`HTTP ${signalsRes.status}`);
        const metricsData = await metricsRes.json();
        const signalsData = await signalsRes.json();
        if (!cancelled) {
          setMetrics(metricsData);
          setSignals(signalsData.signals ?? []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load journal');
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    poll();
    const interval = setInterval(poll, JOURNAL_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled]);

  return { metrics, signals, loading, error };
}
