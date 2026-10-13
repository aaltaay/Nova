/**
 * The Market page's read (ADR 053): the board for the blocks' current switches, polled while the page shows and
 * the window is visible -- the backend refreshes its reads only while someone asks, so a hidden page costs
 * nothing. A switch change asks at once and keeps the last answer on screen until the new one lands. A failed read
 * keeps the last good answer and says so in `error`. The sample desk reads nothing live.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { MARKET_BOARD_PATH, MARKET_LOADING_POLL_MS, MARKET_POLL_MS, MARKET_SCHEMA_VERSION } from './constants';
import { sampleMarketBoard } from './sampleMarket';
import type { BlockPeriods, MarketBoard } from './types';

export interface MarketRead {
  data: MarketBoard | null;
  error: string | null;
  /** The backend has no such route (an API from before ADR 053). */
  unavailable: boolean;
}

export function normalizeBoard(raw: unknown): MarketBoard | null {
  if (!raw || typeof raw !== 'object') return null;
  const b = raw as Partial<MarketBoard>;
  if (b.schema_version !== MARKET_SCHEMA_VERSION) return null;
  if (!b.session || !b.day_read || !Array.isArray(b.quotes) || !b.breadth || !b.sectors || !b.industries || !b.top) {
    return null;
  }
  return b as MarketBoard;
}

export function boardUrl(p: BlockPeriods): string {
  const q = new URLSearchParams({
    sectors: p.sectors,
    industries: p.industries,
    climate: p.climate,
    top: p.top.kind,
    top_period: p.top.period,
  });
  return `${MARKET_BOARD_PATH}?${q.toString()}`;
}

export function useMarketBoard(periods: BlockPeriods): MarketRead {
  const sample = useSampleRoute();
  const url = sample ? null : boardUrl(periods);
  const [state, setState] = useState<MarketRead>({ data: null, error: null, unavailable: false });
  const lastRef = useRef<MarketBoard | null>(null);

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const schedule = (ms: number) => {
      if (cancelled) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void read(), ms);
    };
    const delay = () => (lastRef.current && !lastRef.current.loading ? MARKET_POLL_MS : MARKET_LOADING_POLL_MS);

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
        setState({ data: body, error: null, unavailable: false });
      } catch (e) {
        if (!cancelled) {
          setState((s) => ({ ...s, error: `The market board did not load: ${e instanceof Error ? e.message : String(e)}` }));
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

  const sampleRead = useMemo<MarketRead>(
    () => ({ data: sample ? sampleMarketBoard(periods) : null, error: null, unavailable: false }),
    [sample, periods],
  );
  return sample ? sampleRead : state;
}
