/**
 * Session VWAP shared by every chart pane.
 *
 * Closed minutes come from ``CHART_VWAP_SOURCE_TIMEFRAME`` so every pane still
 * anchors at 09:30 ET. Sub-minute panes then splice in their own bars for the
 * visible window -- otherwise VWAP is a once-per-minute staircase that stops
 * while 10Sec candles keep painting. Coarser panes keep sampling the 1Min
 * series (one VWAP point per painted candle). Accumulating from each pane's
 * own window with no session anchor was the old per-timeframe drift.
 */
import type { LineData, Time } from 'lightweight-charts';
import {
  CHART_VWAP_SESSION_END_SEC,
  CHART_VWAP_SESSION_START_SEC,
  CHART_VWAP_SOURCE_TIMEFRAME,
} from '../constants';
import type { IndicatorBar } from '../chartIndicators';
import {
  isDailyTimeframe,
  isSubMinuteTimeframe,
  timeframeSeconds,
} from '../tickerChartData';

export interface VwapPoint {
  time: number;
  value: number;
}

const SEC_PER_DAY = 86_400;

/**
 * ``IndicatorBar.time`` is ET wall clock encoded as an epoch (``isoToEtTime``),
 * so UTC getters read ET directly and each bar's DST offset is already folded in.
 */
function etDayKey(time: number): number {
  const d = new Date(time * 1000);
  return d.getUTCFullYear() * 10_000 + d.getUTCMonth() * 100 + d.getUTCDate();
}

function etSecondsOfDay(time: number): number {
  return ((time % SEC_PER_DAY) + SEC_PER_DAY) % SEC_PER_DAY;
}

function latestDayKey(bars: IndicatorBar[]): number {
  for (let i = bars.length - 1; i >= 0; i -= 1) {
    if (Number.isFinite(bars[i].time)) return etDayKey(bars[i].time);
  }
  return -1;
}

/**
 * Running session VWAP per source bar, resetting each ET day at the RTH open.
 * Premarket bars produce no point (nothing to anchor yet); zero-volume bars and
 * post-close bars carry the previous value forward.
 */
export function sessionVwapPoints(minuteBars: IndicatorBar[]): VwapPoint[] {
  const out: VwapPoint[] = [];
  let cumPriceVolume = 0;
  let cumVolume = 0;
  let value = NaN;
  let day = -1;

  for (const bar of minuteBars) {
    const time = bar.time;
    if (!Number.isFinite(time)) continue;

    const key = etDayKey(time);
    if (key !== day) {
      cumPriceVolume = 0;
      cumVolume = 0;
      value = NaN;
      day = key;
    }

    const secondOfDay = etSecondsOfDay(time);
    if (secondOfDay < CHART_VWAP_SESSION_START_SEC) continue;

    if (secondOfDay < CHART_VWAP_SESSION_END_SEC) {
      const volume = Number(bar.volume);
      if (Number.isFinite(volume) && volume > 0) {
        cumPriceVolume += ((bar.high + bar.low + bar.close) / 3) * volume;
        cumVolume += volume;
      }
    }

    if (cumVolume > 0) value = cumPriceVolume / cumVolume;
    if (Number.isFinite(value)) out.push({ time, value });
  }

  return out;
}

/**
 * Map session VWAP onto a pane's bars. A pane bar takes the newest source point
 * that closed inside it, so a coarse bar shows the VWAP as of its own close and
 * sub-minute bars step once per source bar. Returns `[]` for daily and above --
 * a single-session VWAP has no meaning there.
 */
/**
 * Sub-minute panes need their own bars in the accumulator or VWAP is a
 * once-per-minute staircase that sits still while 10Sec candles keep painting.
 * 1Min bars before the pane window stay in so a 4-hour 10Sec slice still
 * anchors at 09:30. Coarser panes keep the 1Min series -- one point per
 * painted candle is already walking with those bars.
 */
export function vwapSourceForPane(
  minuteBars: IndicatorBar[],
  paneBars: IndicatorBar[],
  timeframe: string,
): IndicatorBar[] {
  if (!isSubMinuteTimeframe(timeframe) || paneBars.length === 0) {
    return minuteBars;
  }
  const paneStart = paneBars[0].time;
  if (!Number.isFinite(paneStart)) return minuteBars;
  const sourceSec = timeframeSeconds(CHART_VWAP_SOURCE_TIMEFRAME);
  const head = minuteBars.filter(
    (bar) => Number.isFinite(bar.time) && bar.time + sourceSec <= paneStart,
  );
  return [...head, ...paneBars];
}

export function sampleVwapOntoBars(
  points: VwapPoint[],
  paneBars: IndicatorBar[],
  timeframe: string,
  options?: { extendToTime?: number },
): LineData<Time>[] {
  if (isDailyTimeframe(timeframe)) return [];
  if (points.length === 0 || paneBars.length === 0) return [];

  const bucket = timeframeSeconds(timeframe);
  const out: LineData<Time>[] = [];
  let index = 0;
  let value = NaN;
  let valueDay = -1;

  for (const bar of paneBars) {
    const time = bar.time;
    if (!Number.isFinite(time)) continue;
    const cutoff = time + bucket;
    while (index < points.length && points[index].time < cutoff) {
      value = points[index].value;
      valueDay = etDayKey(points[index].time);
      index += 1;
    }
    if (!Number.isFinite(value)) continue;
    // Yesterday's close must not bleed across today's premarket.
    if (etDayKey(time) !== valueDay) continue;
    out.push({ time: time as Time, value });
  }

  const extendToTime = options?.extendToTime;
  if (
    out.length > 0
    && extendToTime != null
    && Number.isFinite(extendToTime)
  ) {
    const last = out[out.length - 1];
    const lastTime = last.time as number;
    if (extendToTime > lastTime && etDayKey(extendToTime) === etDayKey(lastTime)) {
      out.push({ time: extendToTime as Time, value: last.value });
    }
  }

  return out;
}

/**
 * Whether the source bars reach the newest day's RTH open. False means the store
 * window starts mid-session, so the line understates real session volume and has
 * to say so instead of passing as authoritative.
 */
export function coversSessionOpen(minuteBars: IndicatorBar[]): boolean {
  const day = latestDayKey(minuteBars);
  if (day < 0) return false;

  let earliest = Number.POSITIVE_INFINITY;
  for (const bar of minuteBars) {
    if (!Number.isFinite(bar.time)) continue;
    if (etDayKey(bar.time) !== day) continue;
    earliest = Math.min(earliest, etSecondsOfDay(bar.time));
  }
  return earliest <= CHART_VWAP_SESSION_START_SEC;
}
