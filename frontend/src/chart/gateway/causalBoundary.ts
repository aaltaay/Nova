import type { Time } from 'lightweight-charts';
import { isoToEtTime, type RawBar } from '../../tickerChartData';

/** Entire later/crossing candles stay contextual even when a decision bucket is missing. */
export function causalBoundary(
  bars: RawBar[], asOfIso: string | undefined, timeframe: '1Min' | '5Min',
  coordinate: (time: Time) => number | null, barSpacing: number, plotWidth: number,
): { x: number; hasFuture: boolean } | null {
  if (!bars.length || asOfIso == null) return null;
  const asOf = Date.parse(asOfIso);
  const duration = timeframe === '5Min' ? 300000 : 60000;
  const future = bars.find(bar => timeframe === '5Min'
    ? Date.parse(bar.t) + duration > asOf : Date.parse(bar.t) >= asOf);
  const clamp = (x: number) => Math.max(0, Math.min(plotWidth, x));
  if (future) {
    const x = coordinate(isoToEtTime(future.t, false));
    // An unavailable coordinate cannot make actual future candles look causal.
    return { x: x == null ? 0 : clamp(x - barSpacing / 2), hasFuture: true };
  }
  const last = coordinate(isoToEtTime(bars[bars.length - 1].t, false));
  return last == null ? null : { x: clamp(last + barSpacing / 2), hasFuture: false };
}
