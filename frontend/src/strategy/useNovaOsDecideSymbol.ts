/**
 * Poll a single-symbol Nova OS decide endpoint for Trader.
 * Clears prior decision immediately on symbol switch (no cross-symbol bleed).
 */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, NOVA_OS_TRADER_DECIDE_POLL_MS } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { NovaOsDecision } from './types';

const DECIDE_API = `${API_BASE_URL}/api/nova-os/decide`;

export interface UseNovaOsDecideSymbolReturn {
  decision: NovaOsDecision | null;
  loading: boolean;
  error: string | null;
  /** HTTP status when last failure was a non-2xx (e.g. 404 not in scanner). */
  errorStatus: number | null;
  /** Epoch ms of last successful decision payload. */
  updatedAt: number | null;
  refresh: () => void;
}

export function useNovaOsDecideSymbol(
  symbol: string | null | undefined,
  enabled = true,
): UseNovaOsDecideSymbolReturn {
  const sample = useSampleDataOptional();
  const [decision, setDecision] = useState<NovaOsDecision | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const inFlight = useRef(false);
  const symbolKey = (symbol ?? '').trim().toUpperCase();

  // Clear immediately when the symbol key changes so UI never shows prior name.
  useEffect(() => {
    if (sample) return;
    setDecision(null);
    setError(null);
    setErrorStatus(null);
    setUpdatedAt(null);
    setLoading(Boolean(enabled && symbolKey));
  }, [sample, symbolKey, enabled]);

  useEffect(() => {
    if (sample || !enabled || !symbolKey) {
      setLoading(false);
      return;
    }
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const res = await fetch(`${DECIDE_API}/${encodeURIComponent(symbolKey)}`);
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            if (typeof body?.detail === 'string') detail = body.detail;
          } catch {
            /* keep status text */
          }
          if (!cancelled) {
            setDecision(null);
            setError(detail);
            setErrorStatus(res.status);
          }
          return;
        }
        const data = (await res.json()) as NovaOsDecision;
        if (!cancelled) {
          setDecision(data);
          setError(null);
          setErrorStatus(null);
          setUpdatedAt(Date.now());
        }
      } catch (err) {
        if (!cancelled) {
          setDecision(null);
          setError(err instanceof Error ? err.message : 'Failed to load Nova OS decision');
          setErrorStatus(null);
        }
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    poll();
    const interval = setInterval(poll, NOVA_OS_TRADER_DECIDE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sample, enabled, symbolKey, tick]);

  if (sample) {
    const d = symbolKey ? sample.decisionForSymbol(symbolKey) : null;
    return {
      decision: d,
      loading: false,
      error: d ? null : symbolKey ? `${symbolKey} not in sample decide fixtures` : null,
      errorStatus: d || !symbolKey ? null : 404,
      updatedAt: Date.now(),
      refresh: () => {},
    };
  }

  return {
    decision,
    loading,
    error,
    errorStatus,
    updatedAt,
    refresh: () => setTick((t) => t + 1),
  };
}
