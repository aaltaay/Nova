/**
 * Adapters around lightweight-charts-indicators (EMA / RSI / MACD).
 * Calculation stays in the library — this file only maps Nova bars ↔ plot series.
 * VWAP is the exception: it needs one session-anchored series shared by every
 * timeframe, which the library's per-array cumulative indicator cannot give.
 * See `chart/vwapSession.ts`.
 */
import { EMA, MACD, RSI } from 'lightweight-charts-indicators';
import type { Time, LineData, HistogramData, WhitespaceData } from 'lightweight-charts';
import type { Bar } from 'oakscriptjs';
import {
  CHART_EMA_LENGTHS,
  CHART_MACD_FAST,
  CHART_MACD_SIGNAL,
  CHART_MACD_SLOW,
  CHART_RSI_LENGTH,
  CHART_VWAP_SESSION_START_SEC,
  type ChartEmaLength,
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
    const numeric = typeof t === 'number'
      ? t
      : Date.parse(`${String(t)}T00:00:00Z`) / 1000;
    if (!Number.isFinite(numeric)) continue;
    if (![b.o, b.h, b.l, b.c].every(n => typeof n === 'number' && Number.isFinite(n))) continue;
    out.push({
      time: numeric,
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

const MACD_HIST_UP = '#26A69A';
const MACD_HIST_DOWN = '#FF5252';

/** Keep one slot per price bar so a separate oscillator chart shares logical indices. */
function alignedLinePoints(
  points: Array<{ time: number; value: number }> | undefined,
): Array<LineData<Time> | WhitespaceData<Time>> {
  if (!points) return [];
  return points.map(p =>
    Number.isFinite(p.value)
      ? { time: p.time as Time, value: p.value }
      : { time: p.time as Time },
  );
}

function alignedHistogramPoints(
  points: Array<{ time: number; value: number; color?: string }> | undefined,
): Array<HistogramData<Time> | WhitespaceData<Time>> {
  if (!points) return [];
  return points.map(p => {
    if (!Number.isFinite(p.value)) return { time: p.time as Time };
    return {
      time: p.time as Time,
      value: p.value,
      color: p.color || (p.value >= 0 ? MACD_HIST_UP : MACD_HIST_DOWN),
    };
  });
}

export interface RsiPaneData {
  rsi: Array<LineData<Time> | WhitespaceData<Time>>;
}

export interface MacdPaneData {
  histogram: Array<HistogramData<Time> | WhitespaceData<Time>>;
  macd: Array<LineData<Time> | WhitespaceData<Time>>;
  signal: Array<LineData<Time> | WhitespaceData<Time>>;
}

export type EmaOverlayData = Record<ChartEmaLength, LineData<Time>[]>;

export function computeEmaLine(bars: IndicatorBar[], length: ChartEmaLength): LineData<Time>[] {
  const result = EMA.calculate(bars, {
    length,
    src: 'close',
    offset: 0,
    maType: 'None',
    maLength: length,
    bbMult: 2,
  });
  return finiteLinePoints(result.plots.plot0);
}

export function computeEmaOverlays(bars: IndicatorBar[]): EmaOverlayData {
  const out = {} as EmaOverlayData;
  for (const length of CHART_EMA_LENGTHS) {
    out[length] = computeEmaLine(bars, length);
  }
  return out;
}

/**
 * Right-axis tag for the VWAP overlay. Title replaces the numeric last-value.
 * ``partial`` marks a line whose source bars did not reach the session open, so
 * the number understates real session volume.
 */
export function formatVwapAxisTitle(value: number, partial = false): string {
  return `VWAP $${value.toFixed(2)}${partial ? ' (partial)' : ''}`;
}

export function vwapWaitingTitle(): string {
  const hour = Math.floor(CHART_VWAP_SESSION_START_SEC / 3600);
  const minute = Math.floor((CHART_VWAP_SESSION_START_SEC % 3600) / 60);
  const clock = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  return `VWAP (${clock} ET)`;
}

export function vwapAxisTitleFromLine(
  line: Array<LineData<Time> | WhitespaceData<Time>>,
  partial = false,
): string {
  for (let i = line.length - 1; i >= 0; i -= 1) {
    const point = line[i];
    if ('value' in point && Number.isFinite(point.value)) {
      return formatVwapAxisTitle(point.value, partial);
    }
  }
  return vwapWaitingTitle();
}

export function computeRsiPane(bars: IndicatorBar[]): RsiPaneData {
  const result = RSI.calculate(bars, {
    length: CHART_RSI_LENGTH,
    src: 'close',
    calculateDivergence: false,
    maType: 'None',
  });
  return { rsi: alignedLinePoints(result.plots.plot0) };
}

export function computeMacdPane(bars: IndicatorBar[]): MacdPaneData {
  const result = MACD.calculate(bars, {
    fastLength: CHART_MACD_FAST,
    slowLength: CHART_MACD_SLOW,
    signalLength: CHART_MACD_SIGNAL,
    src: 'close',
  });
  return {
    histogram: alignedHistogramPoints(result.plots.plot0),
    macd: alignedLinePoints(result.plots.plot1),
    signal: alignedLinePoints(result.plots.plot2),
  };
}

export function toggleIndicator(
  current: ChartIndicatorId[],
  id: ChartIndicatorId,
): ChartIndicatorId[] {
  return current.includes(id) ? current.filter(x => x !== id) : [...current, id];
}
