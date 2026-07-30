import { describe, expect, it } from 'vitest';
import type { CandlestickData, Time } from 'lightweight-charts';
import { mergeLiveTradeCandle } from './liveTradeApply';
import { clearEtOffsetCacheForTests } from '../tickerChartData';

const tip = (time: Time, close = 10): CandlestickData<Time> => ({
  time,
  open: close,
  high: close,
  low: close,
  close,
});

describe('mergeLiveTradeCandle', () => {
  it('updates matching 10Sec tip and allows forward-jump new candle', () => {
    clearEtOffsetCacheForTests();
    const a = mergeLiveTradeCandle(
      null,
      { price: 1.5, timestamp: '2026-07-29T14:00:05Z' },
      '10Sec',
    );
    expect(a).not.toBeNull();
    const same = mergeLiveTradeCandle(
      a,
      { price: 1.8, timestamp: '2026-07-29T14:00:09Z' },
      '10Sec',
    );
    expect(same?.close).toBe(1.8);
    expect(same?.high).toBe(1.8);
    expect(same?.time).toBe(a!.time);

    // Jump forward ~90s -- must still open a new tip (stale REST tip recovery).
    const jumped = mergeLiveTradeCandle(
      tip(a!.time as Time, 1.8),
      { price: 2.2, timestamp: '2026-07-29T14:01:35Z' },
      '10Sec',
    );
    expect(jumped).not.toBeNull();
    expect(jumped!.time).not.toBe(a!.time);
    expect(jumped!.close).toBe(2.2);
  });

  it('updates 1Day tip when trade falls on the same ET calendar day', () => {
    clearEtOffsetCacheForTests();
    const dayTip = tip('2026-07-29' as Time, 50);
    const next = mergeLiveTradeCandle(
      dayTip,
      { price: 52.75, timestamp: '2026-07-29T21:30:00Z' },
      '1Day',
    );
    expect(next).not.toBeNull();
    expect(next!.time).toBe('2026-07-29');
    expect(next!.close).toBe(52.75);
    expect(next!.high).toBe(52.75);
    expect(next!.open).toBe(50);
  });

  it('does not invent a new daily bar when tip day differs', () => {
    const dayTip = tip('2026-07-28' as Time, 40);
    const next = mergeLiveTradeCandle(
      dayTip,
      { price: 52.75, timestamp: '2026-07-29T21:30:00Z' },
      '1Day',
    );
    expect(next).toBeNull();
  });

  it('rejects out-of-order trades', () => {
    clearEtOffsetCacheForTests();
    const newer = mergeLiveTradeCandle(
      null,
      { price: 1, timestamp: '2026-07-29T14:01:00Z' },
      '10Sec',
    );
    const older = mergeLiveTradeCandle(
      newer,
      { price: 0.5, timestamp: '2026-07-29T14:00:00Z' },
      '10Sec',
    );
    expect(older).toBeNull();
  });
});
