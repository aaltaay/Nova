/**
 * The Cryptos page's reads (ADR 040): the board and one coin's chart, polled while the page shows and the window
 * is visible -- the backend refreshes its sources only while someone asks, so a hidden page costs nothing. A
 * failed read keeps the last good answer on screen and says so in `error`. The sample desk reads nothing live:
 * it shows the approved mockup's figures.
 */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import {
  CRYPTO_BOARD_LOADING_POLL_MS,
  CRYPTO_BOARD_PATH,
  CRYPTO_BOARD_POLL_MS,
  CRYPTO_CANDLES_LOADING_POLL_MS,
  CRYPTO_CANDLES_PATH,
  CRYPTO_CANDLES_POLL_MS,
} from './constants';
import { normalizeBoard, normalizeCandles } from './normalize';
import { SAMPLE_CRYPTO_BOARD, sampleCandles } from './sampleCryptos';
import type { CandleTf, CryptoBoard, CryptoCandles } from './types';

export interface Polled<T> {
  data: T | null;
  error: string | null;
  /** The backend has no such route (an API from before ADR 040). */
  unavailable: boolean;
}

function usePolled<T>(
  url: string | null,
  normalize: (raw: unknown) => T | null,
  nextDelay: (data: T | null) => number,
  what: string,
): Polled<T> {
  const [state, setState] = useState<Polled<T>>({ data: null, error: null, unavailable: false });
  const normalizeRef = useRef(normalize);
  normalizeRef.current = normalize;
  const delayRef = useRef(nextDelay);
  delayRef.current = nextDelay;

  useEffect(() => {
    setState({ data: null, error: null, unavailable: false });
    if (!url) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    let last: T | null = null;

    const schedule = (ms: number) => {
      if (cancelled) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void read(), ms);
    };

    async function read(): Promise<void> {
      if (cancelled) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule(delayRef.current(last));
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
        const body = normalizeRef.current(await res.json());
        if (cancelled) return;
        if (!body) throw new Error(`the ${what} answer is not one Nova can read`);
        last = body;
        setState({ data: body, error: null, unavailable: false });
      } catch (e) {
        if (!cancelled) setState((s) => ({ ...s, error: `The ${what} did not load: ${e instanceof Error ? e.message : String(e)}` }));
      }
      schedule(delayRef.current(last));
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
  }, [url, what]);

  return state;
}

const SAMPLE_BOARD: Polled<CryptoBoard> = { data: SAMPLE_CRYPTO_BOARD, error: null, unavailable: false };

export function useCryptoBoard(): Polled<CryptoBoard> {
  const sample = useSampleRoute();
  const live = usePolled(
    sample ? null : CRYPTO_BOARD_PATH,
    normalizeBoard,
    (b) => (b && !b.loading ? CRYPTO_BOARD_POLL_MS : CRYPTO_BOARD_LOADING_POLL_MS),
    'crypto board',
  );
  return sample ? SAMPLE_BOARD : live;
}

export function useCryptoCandles(symbol: string, tf: CandleTf): Polled<CryptoCandles> {
  const sample = useSampleRoute();
  const q = new URLSearchParams({ symbol, tf }).toString();
  const live = usePolled(
    sample ? null : `${CRYPTO_CANDLES_PATH}?${q}`,
    normalizeCandles,
    (c) => (c && !c.loading ? CRYPTO_CANDLES_POLL_MS : CRYPTO_CANDLES_LOADING_POLL_MS),
    'chart',
  );
  const [sampleData] = useState(() => new Map<string, CryptoCandles>());
  if (!sample) return live;
  const key = `${symbol}:${tf}`;
  if (!sampleData.has(key)) sampleData.set(key, sampleCandles(symbol, tf));
  return { data: sampleData.get(key) ?? null, error: null, unavailable: false };
}
