/**
 * The Global page's read (ADR 060): the board for the chosen period, polled while the page shows and the window is
 * visible. The backend keeps each market's reads on that market's clock; this hook keeps its last answers for the
 * life of the window, so the page opens again at once on what it last showed and the next poll replaces it. A failed
 * read keeps the last good answer and says so in `error`. The sample desk reads nothing live.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { GLOBAL_BOARD_PATH, GLOBAL_LOADING_POLL_MS, GLOBAL_POLL_MS, GLOBAL_SCHEMA_VERSION } from './constants';
import { sampleGlobalBoard } from './sampleGlobal';
import type { GlobalBoard, Period } from './types';

export interface GlobalRead {
  data: GlobalBoard | null;
  error: string | null;
  /** The backend has no such route (an API from before ADR 060). */
  unavailable: boolean;
}

export function normalizeBoard(raw: unknown): GlobalBoard | null {
  if (!raw || typeof raw !== 'object') return null;
  const b = raw as Partial<GlobalBoard>;
  if (b.schema_version !== GLOBAL_SCHEMA_VERSION) return null;
  if (!b.read || !b.world || !Array.isArray(b.regions) || !Array.isArray(b.markets) || !b.sun || !b.budget) return null;
  return b as GlobalBoard;
}

export function boardUrl(period: Period): string {
  return `${GLOBAL_BOARD_PATH}?${new URLSearchParams({ period }).toString()}`;
}

/** The window's last answer per period. Memory only, never storage. */
const kept = new Map<string, GlobalBoard>();

export function resetKeptGlobalBoardsForTests(): void {
  kept.clear();
}

export function useGlobalBoard(period: Period): GlobalRead {
  const sample = useSampleRoute();
  const url = sample ? null : boardUrl(period);
  const [state, setState] = useState<GlobalRead>(() => ({
    data: url ? (kept.get(url) ?? null) : null,
    error: null,
    unavailable: false,
  }));
  const lastRef = useRef<GlobalBoard | null>(state.data);

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
    const delay = () => (lastRef.current && !lastRef.current.loading ? GLOBAL_POLL_MS : GLOBAL_LOADING_POLL_MS);

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
          setState((s) => ({ ...s, error: `The Global page did not load: ${e instanceof Error ? e.message : String(e)}` }));
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

  const sampleRead = useMemo<GlobalRead>(
    () => ({ data: sample ? sampleGlobalBoard(period) : null, error: null, unavailable: false }),
    [sample, period],
  );
  return sample ? sampleRead : state;
}
