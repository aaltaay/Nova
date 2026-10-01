/**
 * Who trades, for the Bots page (ADR 042 F): `GET /api/stock-mode` polled every
 * `BOTS_STOCK_MODES_POLL_MS` while the page is up. A failed read keeps the last
 * rows and says why -- never an empty list that would read "Nova buys nothing".
 * The sample desk has no stock modes and asks nothing.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { BOTS_STOCK_MODES_POLL_MS } from '../constantGroups/bots_page';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { fetchStockModes, type StockModeRow } from './stockModesApi';

export interface StockModesState {
  rows: StockModeRow[];
  /** Why the last read failed; null after a good one. */
  error: string | null;
  /** A read has answered at least once. */
  loaded: boolean;
  refresh: () => void;
}

export function useStockModes(enabled = true): StockModesState {
  const [rows, setRows] = useState<StockModeRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const alive = useRef(true);

  const read = useCallback(async () => {
    try {
      const next = await fetchStockModes();
      if (!alive.current) return;
      setRows(next);
      setError(null);
      setLoaded(true);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error && err.message ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    if (!enabled || onSampleDesk()) return () => { alive.current = false; };
    void read();
    const id = window.setInterval(() => void read(), BOTS_STOCK_MODES_POLL_MS);
    return () => {
      alive.current = false;
      window.clearInterval(id);
    };
  }, [enabled, read]);

  return { rows, error, loaded, refresh: () => void read() };
}
