/**
 * Session VWAP shared by every chart pane.
 *
 * Closed minutes come from ``CHART_VWAP_SOURCE_TIMEFRAME`` so every pane still
 * anchors at 04:00 ET. Sub-minute panes then splice in their own bars for the
 * visible window -- otherwise VWAP is a once-per-minute staircase that stops
 * while 10Sec candles keep painting. Coarser panes keep sampling the 1Min
 * series (one VWAP point per painted candle). Accumulating from each pane's
 * own window with no session anchor was the old per-timeframe drift.
 */
import type { LineData, Time, WhitespaceData } from 'lightweight-charts';
import {
  CHART_VWAP_AFTERHOURS_END_SEC,
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

export type VwapLinePoint = LineData<Time> | WhitespaceData<Time>;

export function hasVwapValue(point: VwapLinePoint): point is LineData<Time> {
  return 'value' in point && Number.isFinite(point.value);
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
 * Running session VWAP per source bar. Resets each ET day at the 04:00
 * premarket open, then again at the 16:00 cash close so after-hours volume
 * cannot overwrite the daytime line (Webull/DAS, D-007). Bars before 04:00
 * produce no point. Zero-volume bars and post-20:00 bars carry the current
 * session's last value forward.
 */
export function sessionVwapPoints(minuteBars: IndicatorBar[]): VwapPoint[] {
  const out: VwapPoint[] = [];
  let cumPriceVolume = 0;
  let cumVolume = 0;
  let value = NaN;
  let day = -1;
  let inAfterHours = false;

  for (const bar of minuteBars) {
    const time = bar.time;
    if (!Number.isFinite(time)) continue;

    const key = etDayKey(time);
    if (key !== day) {
      cumPriceVolume = 0;
      cumVolume = 0;
      value = NaN;
      day = key;
      inAfterHours = false;
    }

    const secondOfDay = etSecondsOfDay(time);
    if (secondOfDay < CHART_VWAP_SESSION_START_SEC) continue;

    const afterCashClose = secondOfDay >= CHART_VWAP_SESSION_END_SEC;
    if (afterCashClose && !inAfterHours) {
      cumPriceVolume = 0;
      cumVolume = 0;
      value = NaN;
      inAfterHours = true;
    }

    const accumulating = afterCashClose
      ? secondOfDay < CHART_VWAP_AFTERHOURS_END_SEC
      : true;
    if (accumulating) {
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
 * Sub-minute panes need their own bars in the accumulator or VWAP is a
 * once-per-minute staircase that sits still while 10Sec candles keep painting.
 * 1Min bars before the pane window stay in so a 4-hour 10Sec slice still
 * anchors at 04:00. Coarser panes keep the 1Min series -- one point per
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

/**
 * Map session VWAP onto a pane's bars. A pane bar takes the newest source point
 * that closed inside it, so a coarse bar shows the VWAP as of its own close and
 * sub-minute bars step once per source bar. Only the newest ET day is painted --
 * leftover from yesterday is not today's VWAP. Skipped bars are whitespace so
 * LineSeries cannot interpolate across the overnight hole. Returns `[]` for
 * daily and above -- a single-session VWAP has no meaning there.
 */
export function sampleVwapOntoBars(
  points: VwapPoint[],
  paneBars: IndicatorBar[],
  timeframe: string,
  options?: { extendToTime?: number },
): VwapLinePoint[] {
  if (isDailyTimeframe(timeframe)) return [];
  if (points.length === 0 || paneBars.length === 0) return [];

  const bucket = timeframeSeconds(timeframe);
  // One session on screen -- leftover from yesterday is not today's VWAP.
  const paintDay = latestDayKey(paneBars);
  const out: VwapLinePoint[] = [];
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
    const barDay = etDayKey(time);
    // Whitespace breaks the line so LineSeries cannot draw a diagonal across
    // the overnight hole (yesterday 23:59 leftover -> today's 04:00).
    if (
      Number.isFinite(value)
      && barDay === valueDay
      && barDay === paintDay
    ) {
      out.push({ time: time as Time, value });
    } else {
      out.push({ time: time as Time });
    }
  }

  const extendToTime = options?.extendToTime;
  if (extendToTime != null && Number.isFinite(extendToTime)) {
    let lastValued: LineData<Time> | undefined;
    for (let i = out.length - 1; i >= 0; i -= 1) {
      const point = out[i];
      if (hasVwapValue(point)) {
        lastValued = point;
        break;
      }
    }
    if (
      lastValued
      && extendToTime > (lastValued.time as number)
      && etDayKey(extendToTime) === etDayKey(lastValued.time as number)
    ) {
      out.push({ time: extendToTime as Time, value: lastValued.value });
    }
  }

  return out.some(hasVwapValue) ? out : [];
}

const SESSION_DAY_LABEL = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });

/**
 * "Sep 21" when a pane's newest bar is on an older ET day than the VWAP
 * source's newest bar, else null. The pane then paints an earlier session's
 * candles and that session's VWAP, which disagreed with the 1-minute pane's
 * today (QA R28, 2026-09-22: TOPS 5-min $1.27, 1-min $1.35, 10-s $1.49 on one
 * screen -- the 5-min and 10-s bars ended the evening before). The pane's VWAP
 * title names its session so no two panes show two VWAPs for "now".
 */
export function paneSessionBehindLabel(
  sourceBars: IndicatorBar[],
  paneBars: IndicatorBar[],
): string | null {
  const sourceDay = latestDayKey(sourceBars);
  const paneDay = latestDayKey(paneBars);
  if (sourceDay < 0 || paneDay < 0 || paneDay >= sourceDay) return null;
  for (let i = paneBars.length - 1; i >= 0; i -= 1) {
    const time = paneBars[i].time;
    if (Number.isFinite(time)) return SESSION_DAY_LABEL.format(new Date(time * 1000));
  }
  return null;
}

/**
 * Whether the source bars reach the newest day's 04:00 ET open. False means the store
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
