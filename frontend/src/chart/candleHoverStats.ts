/**
 * The numbers on a candle's hover card (operator ask, 2026-10-12). Each one is the candle's own or arithmetic
 * on what the chart already holds: the open, high, low, close and volume in the pane's series, the candles
 * before it, the 1-minute bars the session VWAP is built from (`vwapSession.ts`), and the ticker's prior close.
 * A number with no source is absent, never guessed. The one estimate, dollars traded, is marked as one on the
 * card.
 */
import type { Time } from 'lightweight-charts';
import { CHART_VWAP_SESSION_START_SEC, SESSION_RTH_OPEN_MIN_ET } from '../constants';
import type { IndicatorBar } from '../chartIndicators';
import { formatAmPmClock } from './chartTimeFormat';
import { sessionKindFromEtMinutes, type MarketSessionKind } from './sessionHighlight';
import { etDayKey, etSecondsOfDay, type VwapPoint } from './vwapSession';

export interface CandleOhlc {
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface CandleShape {
  /** Close minus open, and that as a fraction of the open. */
  change: number;
  changeFrac: number | null;
  /** High minus low, and that as a fraction of the low. */
  range: number;
  rangeFrac: number | null;
  /** Where the close sits in the range: 0 at the low, 1 at the high; null when the candle has no range. */
  closeInRange: number | null;
  upperWick: number;
  lowerWick: number;
}

export function candleShape(bar: CandleOhlc): CandleShape {
  const { open, high, low, close } = bar;
  const change = close - open;
  const range = high - low;
  return {
    change,
    changeFrac: open > 0 ? change / open : null,
    range,
    rangeFrac: low > 0 ? range / low : null,
    closeInRange: range > 0 ? (close - low) / range : null,
    upperWick: high - Math.max(open, close),
    lowerWick: Math.min(open, close) - low,
  };
}

/** "top 19%" / "bottom 8%" of the range, "at the high" / "at the low"; null when the candle has no range. */
export function closeInRangeLabel(position: number | null): string | null {
  if (position == null || !Number.isFinite(position)) return null;
  const pct = (fraction: number) => Math.max(1, Math.round(fraction * 100));
  if (position >= 0.995) return 'at the high';
  if (position <= 0.005) return 'at the low';
  return position >= 0.5 ? `top ${pct(1 - position)}%` : `bottom ${pct(position)}%`;
}

export interface VolumeVsAverage {
  average: number;
  multiple: number;
  /** How many candles the average is over: fewer than the lookback near the start of the chart. */
  count: number;
}

/** The candle's volume against the average of the candles before it; null without both. */
export function volumeVsAverage(volume: number | null, prior: readonly number[]): VolumeVsAverage | null {
  if (volume == null || !Number.isFinite(volume) || prior.length === 0) return null;
  const average = prior.reduce((sum, v) => sum + v, 0) / prior.length;
  if (!(average > 0)) return null;
  return { average, multiple: volume / average, count: prior.length };
}

/** Shares times the candle's typical price (high + low + close) / 3: an estimate, since prints are not kept. */
export function dollarsTraded(volume: number | null, bar: CandleOhlc): number | null {
  if (volume == null || !(volume > 0)) return null;
  return volume * ((bar.high + bar.low + bar.close) / 3);
}

export interface DayVolume {
  volume: number;
  /** False when the bars start after 04:00 that day: the total is short, as the VWAP line says "partial". */
  fromOpen: boolean;
}

/**
 * The session's volume from 04:00 ET through the candle's close, from the bars the pane's VWAP is built from
 * (`vwapSourceForPane`). Null when those bars do not reach the candle -- a total that stops short of it would
 * read as the candle's own.
 */
export function dayVolumeThrough(bars: readonly IndicatorBar[], candleTime: number, candleEnd: number): DayVolume | null {
  const day = etDayKey(candleTime);
  let volume = 0;
  let earliest = Number.POSITIVE_INFINITY;
  let reachesCandle = false;
  for (const bar of bars) {
    if (!Number.isFinite(bar.time) || etDayKey(bar.time) !== day) continue;
    const second = etSecondsOfDay(bar.time);
    earliest = Math.min(earliest, second);
    if (bar.time >= candleEnd || second < CHART_VWAP_SESSION_START_SEC) continue;
    if (bar.time >= candleTime) reachesCandle = true;
    const shares = bar.volume ?? 0;
    if (Number.isFinite(shares) && shares > 0) volume += shares;
  }
  if (!reachesCandle) return null;
  return { volume, fromOpen: earliest <= CHART_VWAP_SESSION_START_SEC };
}

/** The session VWAP as of the candle's close: the newest point before its end on its own day. */
export function vwapAtClose(points: readonly VwapPoint[], candleTime: number, candleEnd: number): number | null {
  const day = etDayKey(candleTime);
  let value: number | null = null;
  for (const point of points) {
    if (point.time >= candleEnd) break;
    if (etDayKey(point.time) === day && Number.isFinite(point.value)) value = point.value;
  }
  return value;
}

const RTH_OPEN_SEC = SESSION_RTH_OPEN_MIN_ET * 60;
const SECONDS_PER_MINUTE = 60;

/** The open of the 9:30 minute on the candle's day; null for a premarket candle or when that minute has no bar. */
export function regularOpenOf(bars: readonly IndicatorBar[], candleTime: number): number | null {
  if (etSecondsOfDay(candleTime) < RTH_OPEN_SEC) return null;
  const day = etDayKey(candleTime);
  for (const bar of bars) {
    if (!Number.isFinite(bar.time) || etDayKey(bar.time) !== day) continue;
    const second = etSecondsOfDay(bar.time);
    if (second >= RTH_OPEN_SEC && second < RTH_OPEN_SEC + SECONDS_PER_MINUTE) return bar.open;
  }
  return null;
}

const SESSION_LABELS: Record<MarketSessionKind, string> = {
  premarket: 'Premarket',
  rth: 'Regular hours',
  afterhours: 'After hours',
  closed: 'Overnight',
};

/** The session an intraday candle opened in. */
export function candleSession(time: number): { kind: MarketSessionKind; label: string } {
  const d = new Date(time * 1000);
  const kind = sessionKindFromEtMinutes(d.getUTCHours() * 60 + d.getUTCMinutes());
  return { kind, label: SESSION_LABELS[kind] };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;
const TIMEFRAME_UNITS: Record<string, string> = { Sec: 'sec', Min: 'min', Hour: 'hour', Day: 'day', Week: 'week', Month: 'month' };

/** "10 sec", "1 min", "1 day" -- the candle's length, as the card names it. */
export function timeframeLabel(timeframe: string): string {
  const match = timeframe.match(/^(\d+)(Sec|Min|Hour|Day|Week|Month)$/);
  return match ? `${match[1]} ${TIMEFRAME_UNITS[match[2]]}` : timeframe;
}

/** The candle's time as a chart epoch (ET wall clock read as UTC); a daily candle's day at 00:00. */
export function candleEpoch(time: Time): number | null {
  if (typeof time === 'number') return Number.isFinite(time) ? time : null;
  const iso = typeof time === 'string'
    ? time
    : `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
  const ms = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** "Oct 12" for the candle's ET day. */
export function candleDayLabel(epoch: number): string {
  const d = new Date(epoch * 1000);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/** "9:41 AM – 9:42 AM", with seconds on sub-minute candles. */
export function candleClockLabel(epoch: number, seconds: number, showSeconds: boolean): string {
  const clock = (t: number) => {
    const d = new Date(t * 1000);
    return showSeconds
      ? formatAmPmClock(d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds())
      : formatAmPmClock(d.getUTCHours(), d.getUTCMinutes());
  };
  return `${clock(epoch)} – ${clock(epoch + seconds)}`;
}
