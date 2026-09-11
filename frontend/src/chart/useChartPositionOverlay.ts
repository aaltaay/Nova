/**
 * Paint the open IBKR position onto a candle series: avg-cost price line
 * plus session fill arrows. Display only -- never stages or sends an order.
 */
import { useEffect, type RefObject } from 'react';
import {
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts';
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { buildSeriesTimeIndex } from './chartDrawingTime';
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
  bars: readonly { time: Time }[];
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
  const positions = account?.positions ?? [];
  const working = account?.orders ?? [];
  const closed = account?.closedOrders ?? [];
  const position = findOpenPosition(positions, symbol);
  const fills = position ? mergeFills(working, closed, symbol) : [];
  const positionKey = position
    ? `${position.symbol}:${position.qty}:${position.avgCost}:${position.unrealizedPnl ?? ''}`
    : '';
  const fillsKey = fills.map((f) => `${f.orderId}:${f.timeIso}:${f.price}`).join('|');

  useEffect(() => {
    const series = candleSeriesRef.current;
    const next = findOpenPosition(positions, symbol);
    if (!chart || !series || !next) return;
    const line = series.createPriceLine(positionPriceLineOptions(next));
    return () => {
      try {
        series.removePriceLine(line);
      } catch {
        /* chart already disposed */
      }
    };
  }, [chart, candleSeriesRef, symbol, positions, positionKey]);

  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chart || !series) return;
    const plugin = createSeriesMarkers(series, []);
    const next = findOpenPosition(positions, symbol);
    const nextFills = next ? mergeFills(working, closed, symbol) : [];
    if (nextFills.length > 0 && bars.length > 0) {
      plugin.setMarkers(
        seriesMarkersForFills(
          nextFills,
          buildSeriesTimeIndex(bars.map((bar) => bar.time)),
          timeframe,
        ),
      );
    }
    return () => {
      try {
        plugin.setMarkers([]);
        plugin.detach();
      } catch {
        /* chart already disposed */
      }
    };
  }, [
    chart,
    candleSeriesRef,
    symbol,
    positions,
    working,
    closed,
    fillsKey,
    barsRevision, // bar identity; do not depend on the bars array itself
    timeframe,
  ]);

  return position;
}
