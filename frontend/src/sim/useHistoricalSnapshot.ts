import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';
import { SIM_HISTORY_POLL_MS } from './simConstants';

export interface HistoricalSnapshot {
  active: boolean; symbol: string; last: number | null; volume: number | null;
  source: string; as_of: string; error?: string;
  /** Session open/high/low from reached reported prints (or reached candles). */
  open?: number | null; high?: number | null; low?: number | null;
  /** Close of the last daily bar before the session date. */
  prev_close?: number | null;
  selection?: { coverage_through: number; symbol: string; date: string; start: string; end: string };
  prints: {
    time: string; price: number; size: number; exchange: string;
    conditions?: string; unreported?: boolean;
  }[];
}

function blank(symbol: string): HistoricalSnapshot {
  return { active: true, symbol, last: null, volume: null, source: 'loading', as_of: '', prints: [] };
}

/**
 * Historical replay quote + tape for ``symbol`` while Sim has a historical selection.
 * Null until the backend confirms one, so synthetic SIM1 / capture panels never flash.
 */
export function useHistoricalSnapshot(symbol: string, active: boolean) {
  const sim = useIbkrStatus().mode === 'sim';
  const [data, setData] = useState<HistoricalSnapshot | null>(null);
  useEffect(() => {
    if (!sim || !active) return;
    let stopped = false, version = 0;
    async function refresh() {
      const request = ++version;
      try {
        const res = await novaFetch(`${API_BASE_URL}/api/sim/history/snapshot/${encodeURIComponent(symbol)}`);
        if (!res.ok) throw new Error(`Historical replay unavailable (${res.status})`);
        const next = await res.json();
        if (!stopped && request === version) setData(next);
      } catch (error) {
        // Only a known historical selection reports errors; other Sim panels stay put.
        if (!stopped && request === version) {
          setData(prev => prev?.active ? { ...blank(symbol), error: String(error) } : prev);
        }
      }
    }
    // Seek/rewind: drop reached prints at once; later polls rebuild at the new time.
    const seek = () => { version++; setData(prev => prev?.active ? blank(symbol) : prev); void refresh(); };
    seek();
    const id = window.setInterval(() => void refresh(), SIM_HISTORY_POLL_MS);
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, seek);
    return () => { stopped = true; version++; window.clearInterval(id); window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, seek); };
  }, [symbol, sim, active]);
  if (!sim || !active || !data?.active) return null;
  return data.symbol === symbol ? data : blank(symbol);
}
