/**
 * Paint the open IBKR position onto a candle series: avg-cost price line
 * plus session fill arrows. Display only -- never stages or sends an order.
 *
 * Keyed on what is drawn, never on the account's arrays: every account poll
 * hands over new arrays, and re-drawing on each one replaced the price line
 * and the arrows every few seconds on every pane (`FillMarkersPrimitive`
 * says what that cost).
 */
import { useEffect, useRef, type RefObject } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { buildSeriesTimeIndex } from './chartDrawingTime';
import { FillMarkersPrimitive } from './FillMarkersPrimitive';
import {
  findOpenPosition,
  mergeFills,
  positionPriceLineOptions,
  seriesMarkersForFills,
  type ChartPositionSnapshot,
} from './positionOverlay';

interface Args {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  symbol: string;
  timeframe: string;
  bars: readonly { time: Time | number }[];
  barsRevision: number;
}

export function useChartPositionOverlay({
  chart,
  candleSeriesRef,
  symbol,
  timeframe,
  bars,
  barsRevision,
}: Args): ChartPositionSnapshot | null {
  const account = useOptionalIbkrAccountContext();
  const position = findOpenPosition(account?.positions ?? [], symbol);
  const fills = position
    ? mergeFills(account?.orders ?? [], account?.closedOrders ?? [], symbol)
    : [];
  // The line draws the average cost in the side's colour, nothing that moves with the price.
  const lineKey = position ? `${position.symbol}:${position.avgCost}:${position.qty < 0 ? 'short' : 'long'}` : '';
  const fillsKey = fills.map((f) => `${f.orderId}:${f.timeIso}:${f.price}`).join('|');
  const latest = useRef({ position, fills, bars });
  latest.current = { position, fills, bars };

  useEffect(() => {
    const series = candleSeriesRef.current;
    const next = latest.current.position;
    if (!chart || !series || !next) return;
    const line = series.createPriceLine(positionPriceLineOptions(next));
    return () => {
      try {
        series.removePriceLine(line);
      } catch {
        /* chart already disposed */
      }
    };
  }, [chart, candleSeriesRef, symbol, lineKey]);

  const markersRef = useRef<FillMarkersPrimitive | null>(null);
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chart || !series) return;
    const markers = new FillMarkersPrimitive();
    series.attachPrimitive(markers);
    markersRef.current = markers;
    return () => {
      try {
        series.detachPrimitive(markers);
      } catch {
        /* chart already disposed */
      }
      if (markersRef.current === markers) markersRef.current = null;
    };
  }, [chart, candleSeriesRef]);

  useEffect(() => {
    const markers = markersRef.current;
    if (!markers) return;
    const { fills: nextFills, bars: times } = latest.current;
    markers.setMarkers(
      nextFills.length > 0 && times.length > 0
        ? seriesMarkersForFills(nextFills, buildSeriesTimeIndex(times.map((bar) => bar.time as Time)), timeframe)
        : [],
    );
  }, [chart, symbol, fillsKey, barsRevision, timeframe]);

  return position;
}
