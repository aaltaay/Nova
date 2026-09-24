import type {
  CandlestickData,
  HistogramData,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';

export interface RawBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

/** UTC calendar-day cache for America/New_York offset (DST changes are rare). */
const _etOffsetByUtcDay = new Map<string, number>();

export function clearEtOffsetCacheForTests(): void {
  _etOffsetByUtcDay.clear();
}

function etOffsetMs(d: Date): number {
  const day = d.toISOString().slice(0, 10);
  const cached = _etOffsetByUtcDay.get(day);
  if (cached !== undefined) return cached;
  const utcStr = d.toLocaleString('en-US', { timeZone: 'UTC' });
  const etStr = d.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const offset = new Date(etStr).getTime() - new Date(utcStr).getTime();
  _etOffsetByUtcDay.set(day, offset);
  return offset;
}

export function isoToEtTime(iso: string, isDailyOrAbove: boolean): Time {
  if (isDailyOrAbove) return iso.slice(0, 10) as Time;
  const d = new Date(iso);
  return Math.floor((d.getTime() + etOffsetMs(d)) / 1000) as UTCTimestamp;
}

/** ET calendar date ``YYYY-MM-DD`` for an instant (matches daily LWC business-day times). */
export function etCalendarDateString(d: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(d);
  const y = parts.find((p) => p.type === 'year')?.value;
  const m = parts.find((p) => p.type === 'month')?.value;
  const day = parts.find((p) => p.type === 'day')?.value;
  if (!y || !m || !day) return d.toISOString().slice(0, 10);
  return `${y}-${m}-${day}`;
}

/** Coverage ``as_of`` is UTC; show HH:MM in America/New_York (do not slice ISO). */
export function formatCoverageClockEt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const hour = parts.find((p) => p.type === 'hour')?.value;
  const minute = parts.find((p) => p.type === 'minute')?.value;
  if (!hour || !minute) return null;
  return `${hour}:${minute}`;
}

export function timeframeSeconds(timeframe: string): number {
  const match = timeframe.match(/^(\d+)(Sec|Min|Hour)$/);
  if (!match) return 60;
  const n = Number(match[1]);
  if (match[2] === 'Sec') return n;
  if (match[2] === 'Hour') return n * 3600;
  return n * 60;
}

/** Sub-minute timeframes need seconds on axis/crosshair labels. */
export function isSubMinuteTimeframe(timeframe: string): boolean {
  return /^\d+Sec$/.test(timeframe);
}

export function isDailyTimeframe(timeframe: string): boolean {
  return timeframe === '1Day' || timeframe === '1Week' || timeframe === '1Month';
}

/** An instant on the chart's intraday clock: Eastern wall time read as UTC seconds (see isoToEtTime). */
export function etChartSeconds(ms: number): number {
  const d = new Date(ms);
  return Math.floor((ms + etOffsetMs(d)) / 1000);
}

export function tradeBucket(timestamp: string, timeframe: string): Time | null {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  // Daily+ series use business-day strings (see isoToEtTime) -- match that encoding.
  if (isDailyTimeframe(timeframe)) {
    return etCalendarDateString(date) as Time;
  }
  const seconds = etChartSeconds(date.getTime());
  const bucketSize = timeframeSeconds(timeframe);
  return (Math.floor(seconds / bucketSize) * bucketSize) as UTCTimestamp;
}

export function isOutOfOrderTrade(
  previous: CandlestickData<Time> | null,
  nextTime: Time,
): boolean {
  if (previous === null) return false;
  const prevTime = previous.time;
  if (typeof prevTime === 'number' && typeof nextTime === 'number') {
    return nextTime < prevTime;
  }
  // ISO date strings compare lexicographically in calendar order.
  if (typeof prevTime === 'string' && typeof nextTime === 'string') {
    return nextTime < prevTime;
  }
  return false;
}

/** One-pass candles + volumes from REST bars (shared ET conversion). */
export function rawBarsToSeries(
  bars: RawBar[],
  timeframe: string,
): {
  candles: CandlestickData<Time>[];
  volumes: HistogramData<Time>[];
} {
  const daily = isDailyTimeframe(timeframe);
  const candles: CandlestickData<Time>[] = [];
  const volumes: HistogramData<Time>[] = [];
  for (const b of bars) {
    const time = isoToEtTime(b.t, daily);
    candles.push({ time, open: b.o, high: b.h, low: b.l, close: b.c });
    volumes.push({ time, value: b.v, color: volumeBarColor(b.o, b.c) });
  }
  return { candles, volumes };
}

/** A volume bar takes its candle's direction: up (close >= open) green, down red. */
export function volumeBarColor(open: number, close: number): string {
  return close >= open ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)';
}

/**
 * Whether lightweight-charts can apply ``next`` with a single ``series.update``
 * on the newest bar only. Never rewrite older bars -- LWC throws
 * "Cannot update oldest data" if update time is before the series tip.
 */
export function canIncrementalBarsUpdate(prev: RawBar[], next: RawBar[]): boolean {
  if (prev.length === 0 || next.length === 0) return false;
  if (next.length < prev.length) return false;
  if (next.length - prev.length > 1) return false;
  // All bars except the newest must be identical -- any older rewrite needs setData.
  const shared = Math.min(prev.length, next.length) - 1;
  for (let i = 0; i < shared; i++) {
    const a = prev[i];
    const b = next[i];
    if (
      a.t !== b.t
      || a.o !== b.o
      || a.h !== b.h
      || a.l !== b.l
      || a.c !== b.c
      || a.v !== b.v
    ) {
      return false;
    }
  }
  if (next.length === prev.length) return true;
  // Appended one bar: previous tip must be the new second-to-last (closed bar).
  return prev[prev.length - 1].t === next[next.length - 2].t;
}

/**
 * After setData, show a session-sized window -- not the full IB duration.
 * 5Min IB history is 5 calendar days; fitContent of that on a runner looks
 * like one spike on a black pane. 10Sec already is session-sized.
 * 1Min now fetches the full extended session (the session VWAP source needs it),
 * so pin the viewport to the ~500 bars it showed before that change.
 */
export const CHART_PAINT_VISIBLE_BARS: Partial<Record<string, number>> = {
  '1Min': 500,
  '5Min': 96,
  '15Min': 96,
  '30Min': 80,
  '1Hour': 72,
  '1Day': 180,
};

export function timeScaleRangeForSeries(
  timeframe: string,
  candleCount: number,
): { from: number; to: number } | null {
  if (candleCount <= 0) return null;
  const keep = CHART_PAINT_VISIBLE_BARS[timeframe];
  if (!keep || candleCount <= keep) return null;
  return { from: candleCount - keep, to: candleCount - 1 };
}

export function buildMockBars(count: number, basePrice: number): RawBar[] {
  const now = Date.now();
  const stepMs = 5 * 60 * 1000;
  const bars: RawBar[] = [];
  let price = basePrice;
  for (let i = count; i >= 1; i--) {
    const open = price;
    const drift = (Math.sin(i / 3) + Math.cos(i / 5)) * 0.08;
    const close = Math.max(0.5, open + drift);
    const high = Math.max(open, close) + 0.05;
    const low = Math.min(open, close) - 0.05;
    bars.push({
      t: new Date(now - i * stepMs).toISOString(),
      o: Number(open.toFixed(2)),
      h: Number(high.toFixed(2)),
      l: Number(low.toFixed(2)),
      c: Number(close.toFixed(2)),
      v: 10_000 + (i % 7) * 1_500,
    });
    price = close;
  }
  return bars;
}
