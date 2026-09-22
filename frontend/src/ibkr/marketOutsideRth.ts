/**
 * Ticket preflight of the backend's `MKT_OUTSIDE_RTH` refusal (operator
 * decision, 2026-09-21): no exchange takes an unpriced order outside weekday
 * 09:30-16:00 ET and IBKR would hold it until the next open, so the execution
 * door refuses a market order then on every venue -- judged by the venue's
 * clock: the wall clock on Live and Paper, the replay playhead on Sim
 * (`execution/session_gate.py`). The ticket greys Market out ahead of time on
 * all three (QA 2026-09-22, V14: Sim used to stay quiet and offer Market, its
 * default, at a 04:00 playhead the backend then refused). Before the Sim clock
 * has been read the ticket stays quiet and the backend judges.
 */
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import {
  TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON,
  TICKER_TRADE_SESSION_POLL_MS,
} from '../constants';
import { simClockResource } from '../sim/simClockResource';
import type { SimClockState } from '../sim/simClockTypes';
import { isWeekdayRegularHoursNow } from './extendedSession';
import type { IbkrMode } from './types';

/** The Sim playhead as a Date, or null before the clock is read (or when it does not parse). */
export function simPlayhead(clock: SimClockState | null | undefined): Date | null {
  const ms = clock?.sim_time_et ? Date.parse(clock.sim_time_et) : Number.NaN;
  return Number.isFinite(ms) ? new Date(ms) : null;
}

/**
 * The reason Market is refused right now, or null when it is allowed. `now` is
 * the wall clock (Live, Paper); on Sim `simNow` is the playhead, and an unknown
 * playhead leaves the call to the backend.
 */
export function marketOrdersRefusedNow(
  mode: IbkrMode,
  now: Date = new Date(),
  simNow: Date | null = null,
): string | null {
  const clock = mode === 'sim' ? simNow : now;
  if (!clock) return null;
  return isWeekdayRegularHoursNow(clock) ? null : TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON;
}

const noSubscription = () => () => {};

export function useMarketOrdersRefused(mode: IbkrMode): string | null {
  const sim = mode === 'sim';
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : noSubscription()),
    [sim],
  );
  const clock = useSyncExternalStore(subscribe, simClockResource.getSnapshot).data;
  const [wallReason, setWallReason] = useState<string | null>(() => (sim ? null : marketOrdersRefusedNow(mode)));
  useEffect(() => {
    if (sim) return undefined;
    setWallReason(marketOrdersRefusedNow(mode));
    const id = window.setInterval(
      () => setWallReason(marketOrdersRefusedNow(mode)),
      TICKER_TRADE_SESSION_POLL_MS,
    );
    return () => window.clearInterval(id);
  }, [mode, sim]);
  // The Sim clock poll re-renders this hook as the playhead moves.
  return sim ? marketOrdersRefusedNow('sim', new Date(), simPlayhead(clock)) : wallReason;
}
