import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { isoToEtTime, type RawBar } from '../../tickerChartData';
import { causalBoundary } from './causalBoundary';

const bar = (minute: number): RawBar => ({ t: `2022-02-10T15:${String(minute).padStart(2, '0')}:00Z`, o: 2, h: 3, l: 1, c: 2.5, v: 10 });
const coordinate = (bars: RawBar[]) => (time: Time) => {
  const index = bars.findIndex(b => isoToEtTime(b.t, false) === time);
  return index < 0 ? null : 20 + index * 10;
};
describe('future context stays marked across missing decision buckets', () => {
  it('draws no boundary when an as-of timestamp is absent', () => {
    const bars = [bar(10), bar(15)];
    expect(causalBoundary(bars, undefined, '5Min', coordinate(bars), 10, 100)).toBeNull();
  });
  it('masks the first later minute when T itself is missing', () => {
    const bars = [bar(14), bar(17), bar(18)];
    expect(causalBoundary(bars, bar(16).t, '1Min', coordinate(bars), 10, 100)).toEqual({ x: 25, hasFuture: true });
  });
  it('masks an entire crossing 5m candle', () => {
    const bars = [bar(10), bar(15), bar(20)];
    expect(causalBoundary(bars, bar(16).t, '5Min', coordinate(bars), 10, 100)).toEqual({ x: 25, hasFuture: true });
  });
  it('masks the next complete bucket if the crossing bucket is unavailable', () => {
    const bars = [bar(10), bar(20), bar(25)];
    expect(causalBoundary(bars, bar(16).t, '5Min', coordinate(bars), 10, 100)).toEqual({ x: 25, hasFuture: true });
  });
  it('retains a candle ending exactly at T as causal', () => {
    const bars = [bar(10), bar(15), bar(20)];
    expect(causalBoundary(bars, bar(20).t, '5Min', coordinate(bars), 10, 100)).toEqual({ x: 35, hasFuture: true });
  });
  it('places boundary after the last bar only when no displayed future exists', () => {
    const bars = [bar(10), bar(15)];
    expect(causalBoundary(bars, bar(20).t, '5Min', coordinate(bars), 10, 100)).toEqual({ x: 35, hasFuture: false });
  });
  it('fails closed if future candles have unavailable coordinates', () => {
    expect(causalBoundary([bar(17)], bar(16).t, '1Min', () => null, 10, 100)).toEqual({ x: 0, hasFuture: true });
  });
  it('does not invent a boundary for an empty pane', () => {
    expect(causalBoundary([], bar(16).t, '1Min', () => null, 10, 100)).toBeNull();
  });
});
