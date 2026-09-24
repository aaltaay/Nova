/**
 * @vitest-environment jsdom
 */
import { renderHook } from '@testing-library/react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const desk = vi.hoisted(() => ({ mode: 'live' as 'live' | 'paper' | 'sim' }));
const clock = vi.hoisted(() => ({
  data: null as { sim_time_et?: string } | null,
  listeners: new Set<() => void>(),
}));

vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: desk.mode }) }));
vi.mock('../sim/simClockResource', () => ({
  simClockResource: {
    getSnapshot: () => ({ data: clock.data, error: null, stale: false }),
    subscribe: (listener: () => void) => {
      clock.listeners.add(listener);
      return () => clock.listeners.delete(listener);
    },
  },
}));

import { BarCountdownPrimitive } from './BarCountdownPrimitive';
import { useChartBarCountdown } from './useChartBarCountdown';

function fakeSeries() {
  return {
    attachPrimitive: vi.fn(),
    detachPrimitive: vi.fn(),
  } as unknown as ISeriesApi<'Candlestick'> & {
    attachPrimitive: ReturnType<typeof vi.fn>;
    detachPrimitive: ReturnType<typeof vi.fn>;
  };
}

const chartApi = {} as IChartApi;

function mount(timeframe: string, chartActive = true) {
  const series = fakeSeries();
  const candleSeriesRef = { current: series };
  const hook = renderHook(
    (props: { chartActive: boolean }) =>
      useChartBarCountdown({ chartApi, candleSeriesRef, timeframe, chartActive: props.chartActive }),
    { initialProps: { chartActive } },
  );
  return { series, ...hook };
}

describe('useChartBarCountdown', () => {
  let setNow: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-24T13:31:18.400Z'));
    desk.mode = 'live';
    clock.data = null;
    clock.listeners.clear();
    setNow = vi.spyOn(BarCountdownPrimitive.prototype, 'setNow');
  });

  afterEach(() => {
    setNow.mockRestore();
    vi.useRealTimers();
  });

  it('attaches to a minute pane and ticks on the wall clock each second', () => {
    const { series, unmount } = mount('1Min');
    expect(series.attachPrimitive).toHaveBeenCalledTimes(1);
    expect(series.attachPrimitive.mock.calls[0][0]).toBeInstanceOf(BarCountdownPrimitive);
    expect(setNow).toHaveBeenLastCalledWith(Date.parse('2026-09-24T13:31:18.400Z'));

    vi.advanceTimersByTime(610);
    expect(setNow).toHaveBeenLastCalledWith(Date.parse('2026-09-24T13:31:19.005Z'));
    const calls = setNow.mock.calls.length;
    vi.advanceTimersByTime(1000);
    expect(setNow.mock.calls.length).toBe(calls + 1);

    unmount();
    expect(series.detachPrimitive).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(5000);
    expect(setNow.mock.calls.length).toBe(calls + 1);
  });

  it('leaves seconds, hours and days alone', () => {
    for (const tf of ['10Sec', '1Hour', '1Day']) {
      const { series } = mount(tf);
      expect(series.attachPrimitive).not.toHaveBeenCalled();
    }
    expect(setNow).not.toHaveBeenCalled();
  });

  it('stops ticking on a hidden tab', () => {
    const { rerender } = mount('5Min');
    rerender({ chartActive: false });
    expect(setNow).toHaveBeenLastCalledWith(null);
    const calls = setNow.mock.calls.length;
    vi.advanceTimersByTime(5000);
    expect(setNow.mock.calls.length).toBe(calls);
  });

  it('follows the Sim playhead, not the wall clock', () => {
    desk.mode = 'sim';
    clock.data = { sim_time_et: '2026-09-18T10:02:40-04:00' };
    mount('1Min');
    expect(setNow).toHaveBeenLastCalledWith(Date.parse('2026-09-18T14:02:40Z'));

    clock.data = { sim_time_et: '2026-09-18T10:02:50-04:00' };
    for (const listener of clock.listeners) listener();
    expect(setNow).toHaveBeenLastCalledWith(Date.parse('2026-09-18T14:02:50Z'));

    // A paused playhead holds: no wall-clock tick moves it.
    const calls = setNow.mock.calls.length;
    vi.advanceTimersByTime(5000);
    expect(setNow.mock.calls.length).toBe(calls);

    clock.data = null;
    for (const listener of clock.listeners) listener();
    expect(setNow).toHaveBeenLastCalledWith(null);
  });
});
