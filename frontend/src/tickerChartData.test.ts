import { describe, expect, it } from 'vitest';
import type { CandlestickData, Time } from 'lightweight-charts';
import { isOutOfOrderTrade, tradeBucket } from './tickerChartData';

const candle = (time: number): CandlestickData<Time> => ({
  time: time as Time,
  open: 1,
  high: 1,
  low: 1,
  close: 1,
});

describe('ticker chart trade ordering', () => {
  it('rejects a trade bucket older than the latest REST candle', () => {
    expect(isOutOfOrderTrade(candle(1_000), 999 as Time)).toBe(true);
  });

  it('accepts same-bucket and newer trades', () => {
    expect(isOutOfOrderTrade(candle(1_000), 1_000 as Time)).toBe(false);
    expect(isOutOfOrderTrade(candle(1_000), 1_001 as Time)).toBe(false);
  });

  it('rejects an invalid trade timestamp before it reaches the chart library', () => {
    expect(tradeBucket('not-a-date', '1Min')).toBeNull();
  });
});
