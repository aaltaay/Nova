import { describe, expect, it } from 'vitest';
import type { CandlestickData, Time } from 'lightweight-charts';
import {
  countsLiveVolume,
  EMPTY_LIVE_VOLUME,
  mergeLiveTradeCandle,
  restoreLiveTip,
  stepLiveVolume,
  type LiveTip,
} from './liveTradeApply';
import { clearEtOffsetCacheForTests, tradeBucket } from '../tickerChartData';

const tip = (time: Time, close = 10): CandlestickData<Time> => ({
  time,
  open: close,
  high: close,
  low: close,
  close,
});

describe('mergeLiveTradeCandle', () => {
  it('does not invent the first 10Sec candle from a tick', () => {
    clearEtOffsetCacheForTests();
    expect(
      mergeLiveTradeCandle(
        null,
        { price: 1.5, timestamp: '2026-07-29T14:00:05Z' },
        '10Sec',
      ),
    ).toBeNull();
  });

  it('updates matching 10Sec tip and allows forward-jump new candle', () => {
    clearEtOffsetCacheForTests();
    const bucket = tradeBucket('2026-07-29T14:00:05Z', '10Sec');
    expect(bucket).not.toBeNull();
    const a = mergeLiveTradeCandle(
      tip(bucket as Time, 1.4),
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
    const newerBucket = tradeBucket('2026-07-29T14:01:00Z', '10Sec');
    expect(newerBucket).not.toBeNull();
    const older = mergeLiveTradeCandle(
      tip(newerBucket as Time, 1),
      { price: 0.5, timestamp: '2026-07-29T14:00:00Z' },
      '10Sec',
    );
    expect(older).toBeNull();
  });
});

describe('mergeLiveTradeCandle sources (QA 2026-09-22)', () => {
  it('never paints a Level 1 snapshot price: a last is not a print', () => {
    clearEtOffsetCacheForTests();
    const bucket = tradeBucket('2026-09-22T20:07:35Z', '10Sec');
    expect(bucket).not.toBeNull();
    const prev = tip(bucket as Time, 6.9);
    expect(
      mergeLiveTradeCandle(prev, { price: 4.0, timestamp: '2026-09-22T20:07:36Z', source: 'snapshot' }, '10Sec'),
    ).toBeNull();
    // the same price from the print stream (or a replayed print) still paints
    expect(
      mergeLiveTradeCandle(prev, { price: 4.0, timestamp: '2026-09-22T20:07:36Z', source: 'stream' }, '10Sec')?.low,
    ).toBe(4.0);
    expect(
      mergeLiveTradeCandle(prev, { price: 4.0, timestamp: '2026-09-22T20:07:36Z', source: 'sim' }, '10Sec')?.low,
    ).toBe(4.0);
    // an older backend sends no source: a print, as before
    expect(
      mergeLiveTradeCandle(prev, { price: 4.0, timestamp: '2026-09-22T20:07:36Z' }, '10Sec')?.low,
    ).toBe(4.0);
  });
});

describe('stepLiveVolume', () => {
  const at = (iso: string) => tradeBucket(iso, '1Min') as Time;

  it('takes the first day volume as a baseline, not a count', () => {
    const s = stepLiveVolume(EMPTY_LIVE_VOLUME, at('2026-09-24T20:04:10Z'), 1_000_000);
    expect(s).toMatchObject({ mark: 1_000_000, volume: null });
    // Still the bar it joined mid-way: unknown.
    expect(stepLiveVolume(s, s.bar!, 1_050_000).volume).toBeNull();
  });

  it('counts every later bar from its first update', () => {
    let s = stepLiveVolume(EMPTY_LIVE_VOLUME, at('2026-09-24T20:03:50Z'), 1_000_000);
    s = stepLiveVolume(s, at('2026-09-24T20:04:01Z'), 1_010_000);
    expect(s.volume).toBe(10_000);
    s = stepLiveVolume(s, at('2026-09-24T20:04:30Z'), 1_035_000);
    expect(s.volume).toBe(35_000);
  });

  it('keeps the mark over an update with no day volume', () => {
    let s = stepLiveVolume(EMPTY_LIVE_VOLUME, at('2026-09-24T20:03:50Z'), 1_000_000);
    s = stepLiveVolume(s, at('2026-09-24T20:04:01Z'), null);
    expect(s).toMatchObject({ mark: 1_000_000, volume: 0 });
    s = stepLiveVolume(s, at('2026-09-24T20:04:09Z'), 1_020_000);
    expect(s.volume).toBe(20_000);
  });

  it('restarts on a total that went down and leaves that bar unknown', () => {
    let s = stepLiveVolume(EMPTY_LIVE_VOLUME, at('2026-09-24T20:03:50Z'), 1_000_000);
    s = stepLiveVolume(s, at('2026-09-24T20:04:01Z'), 1_010_000);
    s = stepLiveVolume(s, at('2026-09-24T20:04:20Z'), 400);
    expect(s).toMatchObject({ mark: 400, volume: null });
    expect(stepLiveVolume(s, at('2026-09-24T20:05:02Z'), 900).volume).toBe(500);
  });
});

describe('restoreLiveTip', () => {
  const live = (time: number, v: number | null): LiveTip => ({
    candle: { time: time as Time, open: 2.97, high: 3.14, low: 2.9, close: 3.05 },
    volume: v,
  });
  const store = (time: number, v: number | null) => ({
    candle: { time: time as Time, open: 2.98, high: 3.2, low: 2.95, close: 3.07 },
    volume: v,
  });

  it('keeps a live tip newer than the store as drawn', () => {
    expect(restoreLiveTip(store(60, 1), live(120, 90_000))).toEqual(live(120, 90_000));
  });

  it('merges the same bar: the store opened it, the live tip has the last trade', () => {
    expect(restoreLiveTip(store(120, 120_000), live(120, 90_000))).toEqual({
      candle: { time: 120, open: 2.98, high: 3.2, low: 2.9, close: 3.05 },
      volume: 120_000,
    });
    expect(restoreLiveTip(store(120, 80_000), live(120, null))?.volume).toBe(80_000);
  });

  it('drops a live tip the store has moved past', () => {
    expect(restoreLiveTip(store(180, 1), live(120, 90_000))).toBeNull();
  });
});

describe('countsLiveVolume', () => {
  it('counts minute and hour bars, not the tape-built 10Sec or daily', () => {
    expect(countsLiveVolume('1Min')).toBe(true);
    expect(countsLiveVolume('5Min')).toBe(true);
    expect(countsLiveVolume('1Hour')).toBe(true);
    expect(countsLiveVolume('10Sec')).toBe(false);
    expect(countsLiveVolume('1Day')).toBe(false);
  });
});
