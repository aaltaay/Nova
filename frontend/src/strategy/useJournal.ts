/** Polls the Journal panel's three read-only endpoints on an interval — same
 * REST-poll pattern as useWatchlist. `includeMock` opts into synthetic rows
 * seeded by backend/journal/mock_data.py; real endpoints default to
 * excluding them, so this must be an explicit, visible user choice (the
 * "Show demo data" toggle in JournalPanel), never an implicit default. */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, JOURNAL_POLL_INTERVAL_MS, JOURNAL_RECENT_SIGNALS_LIMIT } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { JournalMetrics, JournalSignalRow, JournalTradeRow, RiskStatus } from './types';

const JOURNAL_API = `${API_BASE_URL}/api/journal`;
const STRATEGY_API = `${API_BASE_URL}/api/strategy`;

export interface UseJournalReturn {
  metrics: JournalMetrics | null;
  signals: JournalSignalRow[];
  trades: JournalTradeRow[];
  risk: RiskStatus | null;
  loading: boolean;
  error: string | null;
}

export function useJournal(enabled: boolean, includeMock: boolean): UseJournalReturn {
  const sample = useSampleDataOptional();
  const [metrics, setMetrics] = useState<JournalMetrics | null>(null);
  const [signals, setSignals] = useState<JournalSignalRow[]>([]);
  const [trades, setTrades] = useState<JournalTradeRow[]>([]);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    if (sample || !enabled) return;
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const mockParam = includeMock ? '?include_mock=true' : '';
        const [metricsRes, signalsRes, tradesRes, riskRes] = await Promise.all([
          fetch(`${JOURNAL_API}/metrics${mockParam}`),
          fetch(`${JOURNAL_API}/signals?limit=${JOURNAL_RECENT_SIGNALS_LIMIT}`),
          fetch(`${JOURNAL_API}/trades${mockParam}`),
          fetch(`${STRATEGY_API}/risk`),
        ]);
        for (const res of [metricsRes, signalsRes, tradesRes, riskRes]) {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
        }
        const [metricsData, signalsData, tradesData, riskData] = await Promise.all([
          metricsRes.json(), signalsRes.json(), tradesRes.json(), riskRes.json(),
        ]);
        if (!cancelled) {
          setMetrics(metricsData);
          setSignals(signalsData.signals ?? []);
          setTrades(tradesData.trades ?? []);
          setRisk(riskData);
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
  }, [sample, enabled, includeMock]);

  if (sample) {
    return {
      metrics: null,
      signals: [],
      trades: [],
      risk: null,
      loading: false,
      error: null,
    };
  }

  return { metrics, signals, trades, risk, loading, error };
}
