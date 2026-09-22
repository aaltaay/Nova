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
  trade: { price: number; timestamp: string; source?: string },
  timeframe: string,
): CandlestickData<Time> | null {
  if (!trade.price || !trade.timestamp) return null;
  // A Level 1 snapshot is a last price, not a print. After the close it can be
  // the regular session's last while the tape trades a dollar away; painting
  // it drew a wick no exchange printed (QA 2026-09-22). Candles take prints only.
  if (trade.source === 'snapshot') return null;
  const bucket = tradeBucket(trade.timestamp, timeframe);
  if (bucket === null) return null;
  if (isOutOfOrderTrade(prev, bucket)) return null;

  const price = trade.price;
  const daily = isDailyTimeframe(timeframe);

  // Do not invent the first candle from a tick -- that zooms the empty
  // pane onto "now" so later setData(history) without fitContent looks empty.
  if (!prev) return null;

  if (prev.time === bucket) {
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
