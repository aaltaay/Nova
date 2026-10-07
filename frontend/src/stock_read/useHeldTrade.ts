/**
 * The trade you hold, for one Trader tab (ADR 036 amendment 2026-10-01): what the read is asked about it
 * (`held_*`), the stop you set for it, and trial T1's tape reading, read every second while you hold.
 *
 * The tab remembers, for the holding episode only (never persisted): when it first saw the shares, the
 * stop you set (or the triggered setup's, when you entered at its trigger), and the risk a share your R is
 * measured in -- the first stop under your average it knew (over it, for a short: ADR 048). Flat clears it
 * all, and so does a long turned short.
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
  /** The side held this episode (ADR 048): a long turned short is a new episode. */
  side?: 'long' | 'short' | null;
}

const NONE: HeldTrack = { since: null, stop: null, risk: null, side: null };

export function normalizeFlush(raw: unknown): FlushReading | null {
  const f = obj(raw);
  const at = num(f?.at);
  if (!f || at === null || typeof f.label !== 'string') return null;
  return { at, score: num(f.score), label: str(f.label) ?? 'blind', windowSec: num(f.window_sec) ?? 30 };
}

/** The read's query for the position: empty when nothing is held. A short (a negative quantity) is asked
 * about as `held_side=short` with its shares as a positive count (ADR 048). The stop is the one you set for
 * this tab, else the stop order resting at the broker (`workingStop`). */
export function heldQuery(position: { qty: number; avgCost: number | null } | null, track: HeldTrack,
  workingStop: number | null = null): string {
  if (!position || !position.qty || position.avgCost === null || !(position.avgCost > 0)) return '';
  const q = new URLSearchParams({ held_qty: String(Math.abs(position.qty)), held_avg: String(position.avgCost) });
  const stop = track.stop ?? workingStop;
  if (stop !== null && stop > 0) q.set('held_stop', String(stop));
  if (track.risk !== null && track.risk > 0) q.set('held_risk', String(track.risk));
  if (track.since !== null) q.set('held_since', String(Math.floor(track.since)));
  if (position.qty < 0) q.set('held_side', 'short');
  return q.toString();
}

/** A stop the plan entered at: the triggered setup's own, on its own side, when the shares came in while it
 * triggered. */
function triggeredStop(plan: StockPlan | null, side: 'long' | 'short'): number | null {
  return plan && plan.source === 'setup' && plan.state === 'triggered' && (plan.side ?? 'long') === side
    ? plan.stop : null;
}

export function useHeldTrade(opts: {
  symbol: string;
  live: boolean;
  position: { qty: number; avgCost: number | null } | null;
  read: StockRead | null;
  /** The stop order resting at the broker that protects the position (`protectiveStop`). */
  workingStop?: number | null;
}): {
  track: HeldTrack;
  query: string;
  setStop: (stop: number | null) => void;
  flush: PolledState<FlushReading>;
} {
  const { symbol, live, position, read } = opts;
  const workingStop = opts.workingStop ?? null;
  const [track, setTrack] = useState<HeldTrack>(NONE);
  const side: 'long' | 'short' | null = !position || !position.qty ? null : position.qty > 0 ? 'long' : 'short';
  const avg = position?.avgCost ?? null;

  useEffect(() => setTrack(NONE), [symbol]);
  useEffect(() => {
    setTrack(prev => {
      if (side === null) return prev.since === null ? prev : NONE;
      if (prev.since !== null && (prev.side ?? 'long') === side) return prev;
      return { since: Date.now() / 1000, stop: triggeredStop(read?.plan ?? null, side), risk: null, side };
    });
  }, [side, read?.plan]);
  // R is measured in the first stop on the losing side of your average the tab knew (under a long's, over a
  // short's); it does not move with the stop.
  const heldStop = read?.held?.stop?.price ?? null;
  useEffect(() => {
    if (side === null || avg === null || heldStop === null) return;
    const risk = side === 'short' ? heldStop - avg : avg - heldStop;
    if (!(risk > 0)) return;
    setTrack(prev => (prev.risk !== null || prev.since === null ? prev : { ...prev, risk: Math.round(risk * 1e4) / 1e4 }));
  }, [side, avg, heldStop]);

  const setStop = useCallback((stop: number | null) => {
    setTrack(prev => ({ ...prev, stop: stop !== null && stop > 0 ? stop : null }));
  }, []);
  const query = useMemo(() => heldQuery(position, track, workingStop), [position, track, workingStop]);
  const sym = symbol.trim().toUpperCase();
  // Trial T1's flush call is a long's (sellers flushing the tape): a short reads none.
  const long = side === 'long';
  const flush = usePolledRead({
    url: sym && long ? `${STOCK_READ_PATH}/${encodeURIComponent(sym)}/flush` : null,
    resetKey: sym,
    normalize: normalizeFlush,
    pollMs: STOCK_READ_FLUSH_POLL_MS,
    active: live && long,
    what: 'tape reading',
  });
  return { track, query, setStop, flush };
}
