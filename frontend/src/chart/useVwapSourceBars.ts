/**
 * The bars every pane's session VWAP is computed from (see ``vwapSession.ts``).
 *
 * Keyed on (symbol, CHART_VWAP_SOURCE_TIMEFRAME) in the shared bars store, so a
 * 5Min pane costs nothing extra when the 1Min pane is already open -- ensureBars
 * dedupes in-flight fetches and the backend already warms 1Min on ticker open
 * (``IBKR_BARS_WARM_TIMEFRAMES``). ``/bars`` is a local store read (ADR 012), so
 * the reconciliation poll here never reaches IBKR on its own.
 */
import { useEffect, useState } from 'react';
import {
  CHART_BARS_CLIENT_STALE_MS,
  CHART_REFETCH_SEC,
  CHART_TIMEFRAME_BAR_LIMITS,
  CHART_VWAP_SOURCE_TIMEFRAME,
} from '../constants';
import { rawBarsToIndicatorBars, type IndicatorBar } from '../chartIndicators';
import { ensureBars, getBarsEntry, invalidateBars, isBarsEntryFresh, subscribeBars } from './barsStore';
import { coversSessionOpen } from './vwapSession';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { SIM_CHART_REFRESH_MS, SIM_CLOCK_SCRUB_EVENT } from '../sim/simClockEvents';

export interface VwapSource {
  bars: IndicatorBar[];
  revision: number;
  /** False when the window starts mid-session -- the line must say "partial". */
  coversOpen: boolean;
}

const EMPTY: VwapSource = { bars: [], revision: 0, coversOpen: false };

export function useVwapSourceBars(symbol: string, active: boolean): VwapSource {
  const sim = useIbkrStatus().mode === 'sim';
  const [source, setSource] = useState<VwapSource>(EMPTY);

  useEffect(() => {
    const timeframe = CHART_VWAP_SOURCE_TIMEFRAME;
    // Symbol gate -- never leave the prior ticker's VWAP on screen.
    setSource(EMPTY);
    if (!active || !symbol) return;

    let alive = true;
    const controller = new AbortController();

    const apply = () => {
      const entry = getBarsEntry(symbol, timeframe);
      if (!alive) return;
      if (!entry || Boolean(entry.coverage?.replay) !== sim) {
        setSource(EMPTY);
        return;
      }
      const bars = rawBarsToIndicatorBars(entry.bars, timeframe);
      setSource({
        bars,
        revision: entry.revision,
        coversOpen: coversSessionOpen(bars),
      });
    };

    const refresh = () => {
      const entry = getBarsEntry(symbol, timeframe);
      if (!sim && entry && entry.bars.length > 0 && isBarsEntryFresh(entry, CHART_BARS_CLIENT_STALE_MS)) {
        return;
      }
      void ensureBars(
        symbol,
        timeframe,
        controller.signal,
        CHART_TIMEFRAME_BAR_LIMITS[timeframe],
      ).catch(() => {
        // The pane surfaces bar errors for its own timeframe; a missing VWAP
        // source just means no line, which the axis title already shows.
      });
    };

    const onScrub = () => {
      invalidateBars(symbol, timeframe);
      setSource(EMPTY);
      refresh();
    };
    const unsubscribe = subscribeBars(symbol, timeframe, apply);
    onScrub();
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, onScrub);

    const seconds = CHART_REFETCH_SEC[timeframe];
    const interval = sim ? SIM_CHART_REFRESH_MS : (seconds ?? 0) * 1000;
    const timer = interval ? setInterval(refresh, interval) : null;

    return () => {
      alive = false;
      controller.abort();
      unsubscribe();
      window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, onScrub);
      if (timer) clearInterval(timer);
    };
  }, [symbol, active, sim]);

  return source;
}
