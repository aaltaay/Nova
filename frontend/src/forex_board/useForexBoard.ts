/**
 * The Forex page's read (ADR 061): the board for the chosen period, polled while the page shows and the window is
 * visible. The backend keeps each currency's reads on the FX day's clock; this hook keeps its last answers for the
 * life of the window, so the page opens again at once on what it last showed and the next poll replaces it. A failed
 * read keeps the last good answer and says so in `error`. The sample desk reads nothing live.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { FOREX_BOARD_PATH, FOREX_LOADING_POLL_MS, FOREX_POLL_MS, FOREX_SCHEMA_VERSION } from './constants';
import { sampleForexBoard } from './sampleForex';
import type { ForexBoard, Period } from './types';

export interface ForexRead {
  data: ForexBoard | null;
  error: string | null;
  /** The backend has no such route (an API from before ADR 061). */
  unavailable: boolean;
}

export function normalizeBoard(raw: unknown): ForexBoard | null {
  if (!raw || typeof raw !== 'object') return null;
  const b = raw as Partial<ForexBoard>;
  if (b.schema_version !== FOREX_SCHEMA_VERSION) return null;
  if (!b.read || !b.market || !b.dollar || !b.fx_day || !Array.isArray(b.sessions) || !Array.isArray(b.currencies)
    || !b.sun || !b.budget) return null;
  return b as ForexBoard;
}

export function boardUrl(period: Period): string {
  return `${FOREX_BOARD_PATH}?${new URLSearchParams({ period }).toString()}`;
}

/** The window's last answer per period. Memory only, never storage. */
const kept = new Map<string, ForexBoard>();

export function resetKeptForexBoardsForTests(): void {
  kept.clear();
}

export function useForexBoard(period: Period): ForexRead {
  const sample = useSampleRoute();
  const url = sample ? null : boardUrl(period);
  const [state, setState] = useState<ForexRead>(() => ({
    data: url ? (kept.get(url) ?? null) : null,
    error: null,
    unavailable: false,
  }));
  const lastRef = useRef<ForexBoard | null>(state.data);

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const same = kept.get(url);
    if (same && same !== lastRef.current) {
      lastRef.current = same;
      setState((s) => ({ ...s, data: same }));
    }
    const schedule = (ms: number) => {
      if (cancelled) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void read(), ms);
    };
    const delay = () => (lastRef.current && !lastRef.current.loading ? FOREX_POLL_MS : FOREX_LOADING_POLL_MS);

    async function read(): Promise<void> {
      if (cancelled) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule(delay());
        return;
      }
      try {
        const res = await fetch(`${API_BASE_URL}${url}`);
        if (cancelled) return;
        if (res.status === 404) {
          setState((s) => ({ ...s, unavailable: true }));
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = normalizeBoard(await res.json());
        if (cancelled) return;
        if (!body) throw new Error('the answer is not one this desk can read');
        lastRef.current = body;
        kept.set(url as string, body);
        setState({ data: body, error: null, unavailable: false });
      } catch (e) {
        if (!cancelled) {
          setState((s) => ({ ...s, error: `The Forex page did not load: ${e instanceof Error ? e.message : String(e)}` }));
        }
      }
      schedule(delay());
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') schedule(0);
    };
    document.addEventListener('visibilitychange', onVisible);
    void read();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [url]);

  const sampleRead = useMemo<ForexRead>(
    () => ({ data: sample ? sampleForexBoard(period) : null, error: null, unavailable: false }),
    [sample, period],
  );
  return sample ? sampleRead : state;
}
