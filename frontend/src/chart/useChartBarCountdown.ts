/**
 * Attach the forming candle's close countdown to a minute chart and drive it
 * from the venue's clock: the wall clock on Live and Paper, ticking on the
 * second; on Sim the replay playhead from the shared clock poll, so a paused
 * replay holds its countdown and a fast one runs it fast.
 */
import { useEffect, useRef } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { simPlayhead, useIbkrStatus } from '../ibkr';
import { simClockResource } from '../sim';
import { BarCountdownPrimitive } from './BarCountdownPrimitive';
import { barCountdownPeriodSec } from './barCountdown';

interface Options {
  /** Non-null once useChartInstance has created the chart (triggers attach). */
  chartApi: IChartApi | null;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  timeframe: string;
  /** Hidden Trader tab: stop ticking. */
  chartActive: boolean;
}

/** Just past the next whole second, so the digits turn with the clock. */
function msToNextSecond(now: number): number {
  return 1000 - (now % 1000) + 5;
}

export function useChartBarCountdown({
  chartApi,
  candleSeriesRef,
  timeframe,
  chartActive,
}: Options): void {
  const primitiveRef = useRef<BarCountdownPrimitive | null>(null);
  const enabled = barCountdownPeriodSec(timeframe) !== null;
  const sim = useIbkrStatus().mode === 'sim';

  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chartApi || !series || !enabled) return undefined;
    const primitive = new BarCountdownPrimitive(timeframe);
    series.attachPrimitive(primitive);
    primitiveRef.current = primitive;
    return () => {
      try {
        series.detachPrimitive(primitive);
      } catch {
        /* chart/series already gone */
      }
      if (primitiveRef.current === primitive) primitiveRef.current = null;
    };
  }, [chartApi, candleSeriesRef, enabled, timeframe]);

  useEffect(() => {
    const primitive = primitiveRef.current;
    if (!primitive) return undefined;
    if (!chartActive) {
      primitive.setNow(null);
      return undefined;
    }
    if (sim) {
      const push = () => primitive.setNow(simPlayhead(simClockResource.getSnapshot().data)?.getTime() ?? null);
      push();
      return simClockResource.subscribe(push);
    }
    let timer = 0;
    const tick = () => {
      const now = Date.now();
      primitive.setNow(now);
      timer = window.setTimeout(tick, msToNextSecond(now));
    };
    tick();
    return () => window.clearTimeout(timer);
  }, [chartApi, enabled, timeframe, chartActive, sim]);
}
