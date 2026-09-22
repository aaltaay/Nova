/**
 * Ticket preflight of the backend's `MKT_OUTSIDE_RTH` refusal (operator
 * decision, 2026-09-21): no exchange takes an unpriced order outside weekday
 * 09:30-16:00 ET and IBKR would hold it until the next open, so the execution
 * door refuses a market order then on every venue. The ticket greys Market out
 * ahead of time on Live and Paper, whose clock is the wall clock. On Sim the
 * clock is the replay playhead, which only the backend judges -- the ticket
 * stays quiet and the refusal, if any, arrives as an ordinary reject.
 */
import { useEffect, useState } from 'react';
import {
  TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON,
  TICKER_TRADE_SESSION_POLL_MS,
} from '../constants';
import { isWeekdayRegularHoursNow } from './extendedSession';
import type { IbkrMode } from './types';

/** The reason Market is refused right now, or null when it is allowed (or Sim, which judges itself). */
export function marketOrdersRefusedNow(mode: IbkrMode, now: Date = new Date()): string | null {
  if (mode === 'sim') return null;
  return isWeekdayRegularHoursNow(now) ? null : TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON;
}

export function useMarketOrdersRefused(mode: IbkrMode): string | null {
  const [reason, setReason] = useState<string | null>(() => marketOrdersRefusedNow(mode));
  useEffect(() => {
    setReason(marketOrdersRefusedNow(mode));
    const id = window.setInterval(
      () => setReason(marketOrdersRefusedNow(mode)),
      TICKER_TRADE_SESSION_POLL_MS,
    );
    return () => window.clearInterval(id);
  }, [mode]);
  return reason;
}
