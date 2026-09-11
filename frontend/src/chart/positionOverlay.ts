/**
 * Pure builders for the open-position overlay on a ticker chart.
 *
 * IBKR `positions()` is the qty / avg-cost SSOT. Fill arrows use session
 * working + closed orders that already have a fill price and time -- never
 * invent a fill candle from avg cost alone.
 */
import { LineStyle, type SeriesMarker, type Time } from 'lightweight-charts';
import type { IbkrOrder, IbkrPosition } from '../ibkr/types';
import { formatSignedMoney } from '../components/globalBarMoney';
import { isoToEtTime, isDailyTimeframe } from '../tickerChartData';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import {
  nearestSeriesTime,
  toCanonicalTime,
  type SeriesTimeIndex,
} from './chartDrawingTime';
import {
  CHART_POSITION_LINE_WIDTH,
  CHART_POSITION_LONG_COLOR,
  CHART_POSITION_MARKER_SIZE,
  CHART_POSITION_SHORT_COLOR,
} from './positionOverlayConstants';

export interface ChartPositionSnapshot {
  symbol: string;
  qty: number;
  avgCost: number;
  unrealizedPnl: number | null;
}

export interface ChartFill {
  orderId: number;
  timeIso: string;
  price: number;
  side: 'BUY' | 'SELL';
  qty: number;
}

export interface ChartPositionLineOptions {
  price: number;
  color: string;
  lineWidth: typeof CHART_POSITION_LINE_WIDTH;
  lineStyle: LineStyle;
  axisLabelVisible: true;
  title: string;
}

export function findOpenPosition(
  positions: readonly IbkrPosition[],
  symbol: string,
): ChartPositionSnapshot | null {
  const needle = symbol.trim().toUpperCase();
  if (!needle) return null;
  for (const row of positions) {
    if ((row.symbol || '').toUpperCase() !== needle) continue;
    if (!Number.isFinite(row.qty) || row.qty === 0) return null;
    if (row.avg_cost == null || !Number.isFinite(row.avg_cost)) return null;
    return {
      symbol: needle,
      qty: row.qty,
      avgCost: row.avg_cost,
      unrealizedPnl: row.unrealized_pnl,
    };
  }
  return null;
}

export function positionLineTitle(position: ChartPositionSnapshot): string {
  const side = position.qty < 0 ? 'Short' : 'Long';
  const qty = formatShareQty(Math.abs(position.qty));
  const avg = formatMoney(position.avgCost);
  if (position.unrealizedPnl == null || !Number.isFinite(position.unrealizedPnl)) {
    return `${side} ${qty} @ ${avg}`;
  }
  return `${side} ${qty} @ ${avg}  ${formatSignedMoney(position.unrealizedPnl)}`;
}

export function positionPriceLineOptions(
  position: ChartPositionSnapshot,
): ChartPositionLineOptions {
  return {
    price: position.avgCost,
    color: position.qty < 0 ? CHART_POSITION_SHORT_COLOR : CHART_POSITION_LONG_COLOR,
    lineWidth: CHART_POSITION_LINE_WIDTH,
    lineStyle: LineStyle.Solid,
    axisLabelVisible: true,
    title: positionLineTitle(position),
  };
}

export function fillsFromOrders(
  orders: readonly IbkrOrder[],
  symbol: string,
): ChartFill[] {
  const needle = symbol.trim().toUpperCase();
  if (!needle) return [];
  const out: ChartFill[] = [];
  for (const row of orders) {
    if ((row.symbol || '').toUpperCase() !== needle) continue;
    const filled = Number(row.filled_qty ?? 0);
    if (!Number.isFinite(filled) || filled <= 0) continue;
    const price = row.avg_fill_price;
    if (price == null || !Number.isFinite(price) || price <= 0) continue;
    const timeIso = row.filled_at ?? row.updated_at;
    if (!timeIso) continue;
    const side = row.side === 'SELL' ? 'SELL' : 'BUY';
    out.push({
      orderId: row.order_id,
      timeIso,
      price,
      side,
      qty: filled,
    });
  }
  return out;
}

/** Closed session rows win when the same order_id is still sitting in Working. */
export function mergeFills(
  working: readonly IbkrOrder[],
  closed: readonly IbkrOrder[],
  symbol: string,
): ChartFill[] {
  const byId = new Map<number, ChartFill>();
  for (const fill of fillsFromOrders(working, symbol)) {
    byId.set(fill.orderId, fill);
  }
  for (const fill of fillsFromOrders(closed, symbol)) {
    byId.set(fill.orderId, fill);
  }
  return [...byId.values()];
}

export function seriesMarkersForFills(
  fills: readonly ChartFill[],
  index: SeriesTimeIndex,
  timeframe: string,
): SeriesMarker<Time>[] {
  if (index.times.length === 0) return [];
  const daily = isDailyTimeframe(timeframe);
  const out: SeriesMarker<Time>[] = [];
  for (const fill of fills) {
    const snapped = nearestSeriesTime(
      index,
      toCanonicalTime(isoToEtTime(fill.timeIso, daily)),
    );
    if (snapped == null) continue;
    const buy = fill.side === 'BUY';
    out.push({
      time: snapped,
      position: buy ? 'belowBar' : 'aboveBar',
      shape: buy ? 'arrowUp' : 'arrowDown',
      color: buy ? CHART_POSITION_LONG_COLOR : CHART_POSITION_SHORT_COLOR,
      text: formatMoney(fill.price),
      size: CHART_POSITION_MARKER_SIZE,
      id: `fill-${fill.orderId}`,
    });
  }
  return out;
}
