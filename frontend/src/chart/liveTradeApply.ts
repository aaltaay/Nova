/**
 * Pure live-trade → candle merge (used by useChartLiveTrade + tests).
 * Forward jumps are allowed for intraday; daily+ only updates the matching tip.
 */
import type { CandlestickData, Time } from 'lightweight-charts';
import {
  isDailyTimeframe,
  isOutOfOrderTrade,
  tradeBucket,
} from '../tickerChartData';

export function mergeLiveTradeCandle(
  prev: CandlestickData<Time> | null,
  trade: { price: number; timestamp: string },
  timeframe: string,
): CandlestickData<Time> | null {
  if (!trade.price || !trade.timestamp) return null;
  const bucket = tradeBucket(trade.timestamp, timeframe);
  if (bucket === null) return null;
  if (isOutOfOrderTrade(prev, bucket)) return null;

  const price = trade.price;
  const daily = isDailyTimeframe(timeframe);

  if (prev && prev.time === bucket) {
    return {
      time: bucket,
      open: prev.open,
      high: Math.max(prev.high, price),
      low: Math.min(prev.low, price),
      close: price,
    };
  }

  // Daily+ bars use business-day string times -- never invent a new period from a tick.
  if (daily) return null;

  // Intraday (incl. 10Sec): any forward bucket opens a new tip candle (gap OK).
  return { time: bucket, open: price, high: price, low: price, close: price };
}
