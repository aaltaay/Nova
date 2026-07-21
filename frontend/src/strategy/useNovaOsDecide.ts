/** Polls Nova OS decide endpoints — signal-only; never places orders. */
import { useEffect, useRef, useState } from 'react';
import {
  API_BASE_URL,
  NOVA_OS_DECIDE_DEFAULT_LIMIT,
  NOVA_OS_DECIDE_POLL_INTERVAL_MS,
} from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { NovaOsDecision } from './types';

const DECIDE_API = `${API_BASE_URL}/api/nova-os/decide`;

export interface NovaOsDecideDataError {
  symbol: string;
  error: string;
}

export interface UseNovaOsDecideReturn {
  decisions: NovaOsDecision[];
  selected: NovaOsDecision | null;
  loading: boolean;
  error: string | null;
  /** Per-symbol bars-unavailable failures the batch endpoint reports
   * separately from `decisions` — see backend/routes/nova_os.py. Loud, not
   * folded into a fake NO_BUY. */
  dataErrors: NovaOsDecideDataError[];
  refresh: () => void;
}

export function useNovaOsDecide(
  enabled: boolean,
  selectedSymbol: string | null,
): UseNovaOsDecideReturn {
  const sample = useSampleDataOptional();
  const [decisions, setDecisions] = useState<NovaOsDecision[]>([]);
  const [selected, setSelected] = useState<NovaOsDecision | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataErrors, setDataErrors] = useState<NovaOsDecideDataError[]>([]);
  const [tick, setTick] = useState(0);
  const inFlight = useRef(false);

  useEffect(() => {
    if (sample || !enabled) return;
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const batchRes = await fetch(`${DECIDE_API}?limit=${NOVA_OS_DECIDE_DEFAULT_LIMIT}`);
        if (!batchRes.ok) throw new Error(`HTTP ${batchRes.status}`);
        const batchData = await batchRes.json();
        let selectedDecision: NovaOsDecision | null = null;
        if (selectedSymbol) {
          const oneRes = await fetch(`${DECIDE_API}/${encodeURIComponent(selectedSymbol)}`);
          if (oneRes.ok) {
            selectedDecision = await oneRes.json();
          } else if (oneRes.status !== 404) {
            throw new Error(`HTTP ${oneRes.status}`);
          }
        }
        if (!cancelled) {
          setDecisions(batchData.decisions ?? []);
          setDataErrors(batchData.errors ?? []);
          setSelected(selectedDecision);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load Nova OS decisions');
        }
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    poll();
    const interval = setInterval(poll, NOVA_OS_DECIDE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sample, enabled, selectedSymbol, tick]);

  if (sample) {
    const sel = selectedSymbol
      ? sample.decisionForSymbol(selectedSymbol)
      : null;
    return {
      decisions: sample.decisions,
      selected: sel,
      loading: false,
      error: null,
      dataErrors: [],
      refresh: () => {},
    };
  }

  return {
    decisions,
    selected,
    loading,
    error,
    dataErrors,
    refresh: () => setTick((t) => t + 1),
  };
}
