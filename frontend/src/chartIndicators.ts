/**
 * Adapters around lightweight-charts-indicators (RSI / MACD and later peers).
 * Calculation stays in the library — this file only maps Nova bars ↔ plot series.
 */
import { RSI, MACD } from 'lightweight-charts-indicators';
import type { Time, LineData, HistogramData } from 'lightweight-charts';
import type { Bar } from 'oakscriptjs';
import {
  CHART_MACD_FAST,
  CHART_MACD_SIGNAL,
  CHART_MACD_SLOW,
  CHART_RSI_LENGTH,
  type ChartIndicatorId,
} from './constants';
import { isoToEtTime, type RawBar } from './tickerChartData';

export interface IndicatorBar extends Bar {
  time: number;
}

export function rawBarsToIndicatorBars(bars: RawBar[], timeframe: string): IndicatorBar[] {
  const daily = timeframe === '1Day' || timeframe === '1Week' || timeframe === '1Month';
  const out: IndicatorBar[] = [];
  for (const b of bars) {
    const t = isoToEtTime(b.t, daily);
    if (typeof t !== 'number') continue;
    if (![b.o, b.h, b.l, b.c].every(n => typeof n === 'number' && Number.isFinite(n))) continue;
    out.push({
      time: t as number,
      open: b.o,
      high: b.h,
      low: b.l,
      close: b.c,
      volume: typeof b.v === 'number' && Number.isFinite(b.v) ? b.v : 0,
    });
  }
  return out;
}

function finiteLinePoints(
  points: Array<{ time: number; value: number }> | undefined,
): LineData<Time>[] {
  if (!points) return [];
  return points
    .filter(p => Number.isFinite(p.value))
    .map(p => ({ time: p.time as Time, value: p.value }));
}

function finiteHistogramPoints(
  points: Array<{ time: number; value: number; color?: string }> | undefined,
): HistogramData<Time>[] {
  if (!points) return [];
  return points
    .filter(p => Number.isFinite(p.value))
    .map(p => ({
      time: p.time as Time,
      value: p.value,
      color: p.color,
    }));
}

export interface RsiPaneData {
  rsi: LineData<Time>[];
}

export interface MacdPaneData {
  histogram: HistogramData<Time>[];
  macd: LineData<Time>[];
  signal: LineData<Time>[];
}

export function computeRsiPane(bars: IndicatorBar[]): RsiPaneData {
  const result = RSI.calculate(bars, {
    length: CHART_RSI_LENGTH,
    src: 'close',
    calculateDivergence: false,
    maType: 'None',
  });
  return { rsi: finiteLinePoints(result.plots.plot0) };
}

export function computeMacdPane(bars: IndicatorBar[]): MacdPaneData {
  const result = MACD.calculate(bars, {
    fastLength: CHART_MACD_FAST,
    slowLength: CHART_MACD_SLOW,
    signalLength: CHART_MACD_SIGNAL,
    src: 'close',
  });
  return {
    histogram: finiteHistogramPoints(result.plots.plot0),
    macd: finiteLinePoints(result.plots.plot1),
    signal: finiteLinePoints(result.plots.plot2),
  };
}

export function toggleIndicator(
  current: ChartIndicatorId[],
  id: ChartIndicatorId,
): ChartIndicatorId[] {
  return current.includes(id) ? current.filter(x => x !== id) : [...current, id];
}
