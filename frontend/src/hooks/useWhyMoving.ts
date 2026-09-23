/**
 * Polls `GET /api/why/{symbol}` (ADR 028) for the Trader's News panel: the rules read of what drove the
 * move -- news, halts, float turnover, a reverse split, short interest and IBKR's borrow market. The
 * sample desk reads nothing live (`unavailable`), and neither does an API from before the route.
 */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, WHY_MOVING_PATH, WHY_MOVING_POLL_MS } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { WhyCheck, WhyCheckState, WhyLikely, WhyMovingRead } from '../types/whyMoving';

export interface WhyMovingState {
  read: WhyMovingRead | null;
  loading: boolean;
  unavailable: boolean;
  /** The last read's failure; the last good answer stays on screen. */
  error: string | null;
}

const STATES: ReadonlySet<string> = new Set<WhyCheckState>(['yes', 'no', 'unknown']);

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function normalizeCheck(raw: unknown): WhyCheck | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const id = str(r.id);
  const label = str(r.label);
  if (!id || !label || typeof r.state !== 'string' || !STATES.has(r.state)) return null;
  return {
    id,
    label,
    state: r.state as WhyCheckState,
    value: str(r.value),
    detail: str(r.detail),
    source: str(r.source) ?? '',
    as_of: num(r.as_of),
  };
}

function normalizeLikely(raw: unknown): WhyLikely | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const kind = str(r.kind);
  const label = str(r.label);
  if (!kind || !label) return null;
  return { kind, label, detail: str(r.detail), confidence: r.confidence === 'likely' ? 'likely' : 'possible' };
}

/** The read off the wire; null when it is not one. */
export function normalizeWhyMoving(raw: unknown): WhyMovingRead | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const likely = normalizeLikely(r.likely);
  if (typeof r.symbol !== 'string' || !likely || !Array.isArray(r.checks)) return null;
  return {
    schema_version: num(r.schema_version) ?? 0,
    symbol: r.symbol,
    generated_at: num(r.generated_at) ?? 0,
    rules_version: str(r.rules_version) ?? '',
    likely,
    checks: r.checks.map(normalizeCheck).filter((c): c is WhyCheck => c !== null),
  };
}

export function useWhyMoving(symbol: string | null | undefined): WhyMovingState {
  const sample = useSampleDataOptional();
  const [read, setRead] = useState<WhyMovingRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const sym = (symbol ?? '').trim().toUpperCase();

  useEffect(() => {
    setRead(null);
    setUnavailable(false);
    setError(null);
    if (sample || !sym) return;
    let cancelled = false;
    setLoading(true);

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const res = await fetch(`${API_BASE_URL}${WHY_MOVING_PATH}/${encodeURIComponent(sym)}`);
        if (res.status === 404) {
          if (!cancelled) setUnavailable(true);  // an API from before the route: no section
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = normalizeWhyMoving(await res.json());
        if (!body) throw new Error('not a move read');
        if (!cancelled && body.symbol === sym) {
          setRead(body);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(`Move read failed: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    void poll();
    const id = window.setInterval(() => void poll(), WHY_MOVING_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [sample, sym]);

  if (sample) return { read: null, loading: false, unavailable: true, error: null };
  return { read, loading, unavailable, error };
}
