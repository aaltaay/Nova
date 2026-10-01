/**
 * The trade you hold, for one Trader tab (ADR 036 amendment 2026-10-01): what the read is asked about it
 * (`held_*`), the stop you set for it, and trial T1's tape reading, read every second while you hold.
 *
 * The tab remembers, for the holding episode only (never persisted): when it first saw the shares, the
 * stop you set (or the triggered setup's, when you bought at its trigger), and the risk a share your R is
 * measured in -- the first stop under your average it knew. Flat clears it all.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { STOCK_READ_FLUSH_POLL_MS, STOCK_READ_PATH } from './constants';
import { num, obj, str } from './normalize';
import { usePolledRead, type PolledState } from './useStockRead';
import type { StockPlan, StockRead } from './types';

export interface FlushReading {
  at: number;
  score: number | null;
  label: string;
  windowSec: number;
}

export interface HeldTrack {
  since: number | null;
  stop: number | null;
  risk: number | null;
}

const NONE: HeldTrack = { since: null, stop: null, risk: null };

export function normalizeFlush(raw: unknown): FlushReading | null {
  const f = obj(raw);
  const at = num(f?.at);
  if (!f || at === null || typeof f.label !== 'string') return null;
  return { at, score: num(f.score), label: str(f.label) ?? 'blind', windowSec: num(f.window_sec) ?? 30 };
}

/** The read's query for the position: empty when nothing is held. */
export function heldQuery(position: { qty: number; avgCost: number | null } | null, track: HeldTrack): string {
  if (!position || !(position.qty > 0) || position.avgCost === null || !(position.avgCost > 0)) return '';
  const q = new URLSearchParams({ held_qty: String(position.qty), held_avg: String(position.avgCost) });
  if (track.stop !== null && track.stop > 0) q.set('held_stop', String(track.stop));
  if (track.risk !== null && track.risk > 0) q.set('held_risk', String(track.risk));
  if (track.since !== null) q.set('held_since', String(Math.floor(track.since)));
  return q.toString();
}

/** A stop the plan bought at: the triggered setup's own, when the shares came in while it triggered. */
function triggeredStop(plan: StockPlan | null): number | null {
  return plan && plan.source === 'setup' && plan.state === 'triggered' ? plan.stop : null;
}

export function useHeldTrade(opts: {
  symbol: string;
  live: boolean;
  position: { qty: number; avgCost: number | null } | null;
  read: StockRead | null;
}): {
  track: HeldTrack;
  query: string;
  setStop: (stop: number | null) => void;
  flush: PolledState<FlushReading>;
} {
  const { symbol, live, position, read } = opts;
  const [track, setTrack] = useState<HeldTrack>(NONE);
  const holding = !!position && position.qty > 0;
  const avg = position?.avgCost ?? null;

  useEffect(() => setTrack(NONE), [symbol]);
  useEffect(() => {
    setTrack(prev => {
      if (!holding) return prev.since === null ? prev : NONE;
      if (prev.since !== null) return prev;
      return { since: Date.now() / 1000, stop: triggeredStop(read?.plan ?? null), risk: null };
    });
  }, [holding, read?.plan]);
  // R is measured in the first stop under your average the tab knew; it does not move with the stop.
  const heldStop = read?.held?.stop?.price ?? null;
  useEffect(() => {
    if (!holding || avg === null || heldStop === null || !(heldStop < avg)) return;
    setTrack(prev => (prev.risk !== null || prev.since === null ? prev : { ...prev, risk: Math.round((avg - heldStop) * 1e4) / 1e4 }));
  }, [holding, avg, heldStop]);

  const setStop = useCallback((stop: number | null) => {
    setTrack(prev => ({ ...prev, stop: stop !== null && stop > 0 ? stop : null }));
  }, []);
  const query = useMemo(() => heldQuery(position, track), [position, track]);
  const sym = symbol.trim().toUpperCase();
  const flush = usePolledRead({
    url: sym && holding ? `${STOCK_READ_PATH}/${encodeURIComponent(sym)}/flush` : null,
    resetKey: sym,
    normalize: normalizeFlush,
    pollMs: STOCK_READ_FLUSH_POLL_MS,
    active: live && holding,
    what: 'tape reading',
  });
  return { track, query, setStop, flush };
}
