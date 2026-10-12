/**
 * @vitest-environment jsdom
 */
import { act, cleanup, renderHook } from '@testing-library/react';
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CANDLE_HOVER_DWELL_MS } from './candleHoverConstants';
import { useCandleHover } from './useCandleHover';

type Move = (p: MouseEventParams<Time>) => void;

/** A candle from $2 (y 200) to $3 (y 100): one price unit is 100 pixels. */
const CANDLE = { open: 2.2, high: 3, low: 2, close: 2.8 };

function setup() {
  let move: Move = () => {};
  const series = { priceToCoordinate: (price: number) => 400 - price * 100 } as unknown as ISeriesApi<'Candlestick'>;
  const chart = {
    subscribeCrosshairMove: vi.fn((fn: Move) => { move = fn; }),
    unsubscribeCrosshairMove: vi.fn(),
  } as unknown as IChartApi;
  const box = document.createElement('div');
  document.body.appendChild(box);
  // The desk's refs are stable (useRef): a new ref each render would start the hover over each time.
  const seriesRef = { current: series };
  const boxRef = { current: box };
  const hook = renderHook(() => useCandleHover(chart, seriesRef, boxRef));
  const at = (logical: number, y: number, extra: Partial<MouseEventParams<Time>> = {}) =>
    act(() => move({
      time: (1000 + logical) as Time,
      logical: logical as never,
      point: { x: 50 + logical * 8, y } as never,
      seriesData: new Map([[series as never, CANDLE as never]]),
      ...extra,
    } as MouseEventParams<Time>));
  const wait = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });
  return { hook, at, wait, box, leave: () => act(() => move({ seriesData: new Map() } as never)) };
}

describe('useCandleHover', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('opens once the pointer rests on one candle', () => {
    const { hook, at, wait } = setup();
    at(10, 150);
    wait(CANDLE_HOVER_DWELL_MS - 1);
    expect(hook.result.current).toBeNull();
    at(10, 152);
    wait(1);
    expect(hook.result.current).toMatchObject({ logical: 10, y: 152 });
  });

  it('never opens on a sweep across candles', () => {
    const { hook, at, wait } = setup();
    for (let i = 0; i < 6; i += 1) {
      at(10 + i, 150);
      wait(CANDLE_HOVER_DWELL_MS / 2);
    }
    expect(hook.result.current).toBeNull();
  });

  it('needs the pointer on the candle, not anywhere in its column', () => {
    const { hook, at, wait } = setup();
    at(10, 40);
    wait(CANDLE_HOVER_DWELL_MS * 2);
    expect(hook.result.current).toBeNull();
  });

  it('follows the pointer to the next candle at once, then closes when it leaves the chart', () => {
    const { hook, at, wait, leave } = setup();
    at(10, 150);
    wait(CANDLE_HOVER_DWELL_MS);
    at(11, 40);
    expect(hook.result.current).toMatchObject({ logical: 11 });
    leave();
    expect(hook.result.current).toBeNull();
  });

  it('closes on a button and stays shut while it is held', () => {
    const { hook, at, wait, box } = setup();
    at(10, 150);
    wait(CANDLE_HOVER_DWELL_MS);
    act(() => { box.dispatchEvent(new Event('pointerdown')); });
    expect(hook.result.current).toBeNull();
    at(10, 150);
    wait(CANDLE_HOVER_DWELL_MS * 2);
    expect(hook.result.current).toBeNull();
    act(() => { window.dispatchEvent(new Event('pointerup')); });
    at(10, 150);
    wait(CANDLE_HOVER_DWELL_MS);
    expect(hook.result.current).not.toBeNull();
  });

  it('gives way to a drawing that tells its own story', () => {
    const { hook, at, wait } = setup();
    at(10, 150);
    wait(CANDLE_HOVER_DWELL_MS);
    at(10, 150, { hoveredObjectId: 'lane:first_pullback' });
    expect(hook.result.current).toBeNull();
  });
});
