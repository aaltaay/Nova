import type {
  CandlestickData,
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

function etOffsetMs(d: Date): number {
  const utcStr = d.toLocaleString('en-US', { timeZone: 'UTC' });
  const etStr = d.toLocaleString('en-US', { timeZone: 'America/New_York' });
  return new Date(etStr).getTime() - new Date(utcStr).getTime();
}

export function isoToEtTime(iso: string, isDailyOrAbove: boolean): Time {
  if (isDailyOrAbove) return iso.slice(0, 10) as Time;
  const d = new Date(iso);
  return Math.floor((d.getTime() + etOffsetMs(d)) / 1000) as UTCTimestamp;
}

function timeframeSeconds(timeframe: string): number {
  const match = timeframe.match(/^(\d+)(Min|Hour)$/);
  if (!match) return 60;
  return match[2] === 'Hour' ? Number(match[1]) * 3600 : Number(match[1]) * 60;
}

export function tradeBucket(timestamp: string, timeframe: string): Time | null {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  const seconds = Math.floor((date.getTime() + etOffsetMs(date)) / 1000);
  const bucketSize = timeframeSeconds(timeframe);
  return (Math.floor(seconds / bucketSize) * bucketSize) as UTCTimestamp;
}

export function isOutOfOrderTrade(
  previous: CandlestickData<Time> | null,
  nextTime: Time,
): boolean {
  return previous !== null
    && typeof previous.time === 'number'
    && typeof nextTime === 'number'
    && nextTime < previous.time;
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
