/**
 * A Top 9 tile's compact 1-minute chart, as plain geometry for an SVG. Pure.
 *
 * Candles are the bars store's 1-minute bars (the Trader's own `/bars`); VWAP is the desk's session
 * VWAP (chart/vwapSession, anchored at 04:00 ET). The window is the last TOP_NINE_CHART_MINUTES
 * minutes up to the board's minute (the snapshot's `asOf`), the same for all nine tiles, so a halted
 * stock's chart ends where the others do. A minute with no trade stays a hole -- nothing is drawn in it.
 */
import type { IndicatorBar } from '../chartIndicators';
import type { VwapPoint } from '../chart';
import { TOP_NINE_CHART_MINUTES } from './topNineConstants';
import type { LuldScale } from './topNineLuld';

export interface ChartBox {
  width: number;
  height: number;
}

export interface CandleShape {
  x: number;
  bodyY: number;
  bodyH: number;
  wickTop: number;
  wickBottom: number;
  volY: number;
  volH: number;
  up: boolean;
}

export interface TopNineChartGeometry {
  candles: CandleShape[];
  bodyW: number;
  /** VWAP polylines, broken where minutes are missing. */
  vwap: string[];
  priceTicks: { y: number; label: string }[];
  timeTicks: { x: number; label: string }[];
  last: { y: number; label: string; up: boolean } | null;
  plotRight: number;
  volTop: number;
  volBottom: number;
  /** The price area's scale, for the LULD band (topNineLuld). */
  scale: LuldScale;
}

export const CHART_AXIS_W = 54;
const LEFT = 6;
const TOP = 8;
const TIME_H = 16;
const VOL_H = 40;
const GAP_BREAK_MIN = 3;
/** A price span under this fraction of the price is a flat chart. */
const FLAT_SPAN = 1e-6;
/** niceStep asks for about four ticks; a few more is a bug, never a chart. */
const MAX_PRICE_TICKS = 12;

function minuteOf(time: number): number {
  return Math.floor(time / 60);
}

function niceStep(span: number, count: number): number {
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (span / (m * mag) <= count) return m * mag;
  }
  return 10 * mag;
}

/** Decimals a price label needs: at least two, more for a sub-dollar step. */
function decimalsFor(step: number): number {
  const text = step.toFixed(6).replace(/0+$/, '');
  const frac = text.split('.')[1] ?? '';
  return Math.max(2, frac.length);
}

export function formatChartPrice(v: number): string {
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

function hhmm(minuteOfEpoch: number): string {
  const d = new Date(minuteOfEpoch * 60_000);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

/**
 * @param bars 1-minute bars, `time` in ET wall-clock seconds (rawBarsToIndicatorBars).
 * @param vwap the session VWAP points for the same bars.
 * @param lastPrice the board's price for the row (the last-price tag), or null to tag the last close.
 * @param endTime the board's minute in the same ET wall-clock seconds; null ends at the newest bar.
 */
export function topNineChartGeometry(
  bars: readonly IndicatorBar[],
  vwap: readonly VwapPoint[],
  lastPrice: number | null,
  box: ChartBox,
  endTime: number | null = null,
): TopNineChartGeometry | null {
  if (!bars.length || box.width < 80 || box.height < 60) return null;
  const endMin = (endTime == null ? minuteOf(bars[bars.length - 1].time) : minuteOf(endTime)) + 1;
  const startMin = endMin - TOP_NINE_CHART_MINUTES;
  const shown = bars.filter((b) => minuteOf(b.time) >= startMin && minuteOf(b.time) < endMin);
  if (!shown.length) return null;
  const vw = vwap.filter((p) => minuteOf(p.time) >= startMin && minuteOf(p.time) < endMin && Number.isFinite(p.value));

  const plotRight = box.width - CHART_AXIS_W;
  const plotW = plotRight - LEFT;
  const volBottom = box.height - TIME_H - 2;
  const volTop = volBottom - VOL_H;
  const priceBottom = volTop - 6;
  const slot = plotW / TOP_NINE_CHART_MINUTES;
  const xOf = (minute: number) => LEFT + (minute - startMin + 0.5) * slot;

  let lo = Math.min(...shown.map((b) => b.low), ...vw.map((p) => p.value));
  let hi = Math.max(...shown.map((b) => b.high), ...vw.map((p) => p.value));
  if (lastPrice != null) {
    lo = Math.min(lo, lastPrice);
    hi = Math.max(hi, lastPrice);
  }
  // A flat chart's VWAP can sit a rounding hair off its price (242.44999999999996 against 242.45):
  // a span that small is flat, or the tick step falls below the price's own rounding.
  const span = hi - lo;
  const pad = span > Math.abs(hi) * FLAT_SPAN ? span * 0.06 : Math.abs(hi) * 0.02 || 0.01;
  lo -= pad;
  hi += pad;
  const yOf = (p: number) => TOP + ((hi - p) / (hi - lo)) * (priceBottom - TOP);

  const vmax = Math.max(1, ...shown.map((b) => b.volume ?? 0));
  const bodyW = Math.max(1.6, slot * 0.62);
  const candles: CandleShape[] = shown.map((b) => {
    const x = xOf(minuteOf(b.time));
    const yo = yOf(b.open);
    const yc = yOf(b.close);
    const volH = ((b.volume ?? 0) / vmax) * (volBottom - volTop);
    return {
      x,
      bodyY: Math.min(yo, yc),
      bodyH: Math.max(1, Math.abs(yc - yo)),
      wickTop: yOf(b.high),
      wickBottom: yOf(b.low),
      volY: volBottom - volH,
      volH,
      up: b.close >= b.open,
    };
  });

  const vwapLines: string[] = [];
  let run: string[] = [];
  let prevMin: number | null = null;
  for (const p of vw) {
    const m = minuteOf(p.time);
    if (prevMin != null && m - prevMin > GAP_BREAK_MIN) {
      if (run.length > 1) vwapLines.push(run.join(' '));
      run = [];
    }
    run.push(`${xOf(m).toFixed(1)},${yOf(p.value).toFixed(1)}`);
    prevMin = m;
  }
  if (run.length > 1) vwapLines.push(run.join(' '));

  const lastBar = shown[shown.length - 1];
  const lastValue = lastPrice ?? lastBar.close;
  const lastY = yOf(lastValue);
  const step = niceStep(hi - lo, 4);
  const dec = decimalsFor(step);
  const priceTicks: { y: number; label: string }[] = [];
  // Counted, not summed: a step the price cannot add must still end the loop.
  const first = Math.ceil(lo / step);
  for (let i = 0; i < MAX_PRICE_TICKS; i += 1) {
    const v = (first + i) * step;
    if (!(v < hi)) break;
    const y = yOf(v);
    if (Math.abs(y - lastY) > 15) priceTicks.push({ y, label: v.toFixed(dec) });
  }
  const timeTicks: { x: number; label: string }[] = [];
  for (let m = Math.ceil(startMin / 30) * 30; m < endMin; m += 30) {
    timeTicks.push({ x: xOf(m) - slot / 2, label: hhmm(m) });
  }
  return {
    candles,
    bodyW,
    vwap: vwapLines,
    priceTicks,
    timeTicks,
    last: { y: lastY, label: formatChartPrice(lastValue), up: lastValue >= lastBar.open },
    plotRight,
    volTop,
    volBottom,
    scale: { startMin, left: LEFT, right: plotRight, slot, top: TOP, bottom: priceBottom, yOf },
  };
}
