/**
 * The historical Level 2 holds the replay depth slot while it is shown
 * (QA R44, 2026-09-22).
 *
 * A bot fires only on a symbol whose depth line the backend holds. A capture
 * replay's Level 2 opens the depth socket, which reserves the replay slot; the
 * historical Level 2 reads the recorded book from the snapshot, so nothing was
 * held and bots were refused "open its Level 2" with the panel open. This asks
 * the backend to hold the slot (`POST /api/sim/history/depth-line`) while the
 * panel is mounted, re-asserts it (a restarted backend forgets it) and lets go
 * on unmount. It opens no IBKR line; a failure is logged, never shown -- the
 * bot gate states the absence itself.
 */
import { useEffect } from 'react';
import { replayPost, replayRequest } from './replayRequest';
import { SIM_HISTORY_DEPTH_LINE_PATH, SIM_HISTORY_DEPTH_LINE_REFRESH_MS } from './simConstants';

function post(symbol: string, hold: boolean): void {
  replayRequest(SIM_HISTORY_DEPTH_LINE_PATH, replayPost({ symbol, hold })).catch((error: unknown) => {
    console.warn(`[Nova] historical depth line ${hold ? 'hold' : 'release'} failed for ${symbol}`, error);
  });
}

export function useHistoricalDepthLine(symbol: string, active: boolean): void {
  const sym = symbol.trim().toUpperCase();
  useEffect(() => {
    if (!active || !sym) return undefined;
    post(sym, true);
    const id = window.setInterval(() => post(sym, true), SIM_HISTORY_DEPTH_LINE_REFRESH_MS);
    return () => {
      window.clearInterval(id);
      post(sym, false);
    };
  }, [sym, active]);
}
