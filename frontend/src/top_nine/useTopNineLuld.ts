/**
 * One tile's LULD trail, read every TOP_NINE_LULD_POLL_MS from `GET /api/luld/{symbol}/trail` -- the band the
 * Trader's 1-minute chart draws. It reads the backend's memory only: no Level 1, Level 2 or tape line is opened for a
 * tile, so a stock Nova holds no tape for answers no band, and the tile says so. A failed read keeps the last answer.
 */
import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { readLuldTrail, type LuldTrail } from '../ibkr';
import { TOP_NINE_LULD_PATH, TOP_NINE_LULD_POLL_MS } from './topNineConstants';

export function useTopNineLuld(symbol: string): LuldTrail | null {
  const [trail, setTrail] = useState<LuldTrail | null>(null);

  useEffect(() => {
    setTrail(null);
    const sym = symbol.trim().toUpperCase();
    if (!sym) return undefined;
    const controller = new AbortController();
    let inFlight = false;
    const read = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await fetch(`${API_BASE_URL}${TOP_NINE_LULD_PATH(sym)}`, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const next = readLuldTrail(await res.json());
        if (next && next.symbol === sym) setTrail(next);
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          console.warn(`[nova] Top 9 LULD band for ${sym} did not load`, err);
        }
      } finally {
        inFlight = false;
      }
    };
    void read();
    const timer = window.setInterval(() => void read(), TOP_NINE_LULD_POLL_MS);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [symbol]);

  return trail;
}
