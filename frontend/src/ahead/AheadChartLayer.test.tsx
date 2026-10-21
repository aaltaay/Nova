/**
 * @vitest-environment jsdom
 *
 * Ahead on a Trader chart pane (ADR 065): asks nothing while off, draws on the 1-minute pane only, hangs the zone on
 * the chart's newest completed candle, widens the room once, and publishes its scene for the panel.
 */
import { act, cleanup, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChartPaneOverlayProps } from '../chart';
import { etChartSeconds } from '../tickerChartData';
import { AheadChartLayer, completedCandles, recentVolumes, useAheadSceneOf } from './AheadChartLayer';
import { AHEAD_KEY_TITLE, AHEAD_WORDS } from './aheadConstants';
import { paneKeySections } from '../stock_read';
import { reloadAheadPrefsForTesting, setAheadPrefs } from './aheadPrefs';
import { hasRoom } from './useAheadRoom';

const asked = vi.fn();
vi.mock('./useAheadAnswer', () => ({
  useAheadAnswer: (symbol: string, enabled: boolean) => {
    asked(symbol, enabled);
    return { answer: null, fetchProblem: null };
  },
}));
vi.mock('../sim', () => ({ useSimReplayDesk: () => false, useSimReplayPlayhead: () => null }));
vi.mock('../stock_read', async (orig) => ({
  ...(await orig<typeof import('../stock_read')>()),
  useStockReadContext: () => ({ symbol: 'XYZ', active: true, readNow: null }),
}));

/** Ten closed minutes ending a minute ago, and the forming one. */
function bars(nowMin = Math.floor(Date.now() / 60_000)) {
  const t0 = etChartSeconds((nowMin - 10) * 60_000);
  return Array.from({ length: 11 }, (_, i) => ({ time: t0 + i * 60, open: 5, high: 5.1, low: 4.9, close: 5 + i / 100 }));
}

function fakePane(nowMin?: number) {
  const data = bars(nowMin);
  const attached: unknown[] = [];
  const ts = {
    timeToIndex: (t: number) => data.findIndex(d => d.time === Number(t)),
    logicalToCoordinate: (l: number) => l * 10,
    getVisibleLogicalRange: () => ({ from: 0, to: 10 }),
    setVisibleLogicalRange: vi.fn(),
    subscribeVisibleLogicalRangeChange: vi.fn(),
    unsubscribeVisibleLogicalRangeChange: vi.fn(),
    subscribeSizeChange: vi.fn(),
    unsubscribeSizeChange: vi.fn(),
    options: () => ({ barSpacing: 10 }),
    height: () => 26,
  };
  const series = {
    data: () => data,
    dataByIndex: (i: number) => data[Math.min(i, data.length - 1)] ?? null,
    priceToCoordinate: (p: number) => 500 - p * 50,
    attachPrimitive: (p: unknown) => attached.push(p),
    detachPrimitive: vi.fn(),
  };
  const chart = { timeScale: () => ts, paneSize: () => ({ width: 600, height: 400 }) };
  return { data, attached, ts, series, chart: chart as unknown as IChartApi };
}

function props(pane: ReturnType<typeof fakePane>, timeframe = '1Min'): ChartPaneOverlayProps {
  const candleSeriesRef = createRef<ISeriesApi<'Candlestick'>>() as { current: ISeriesApi<'Candlestick'> | null };
  candleSeriesRef.current = pane.series as unknown as ISeriesApi<'Candlestick'>;
  return { symbol: 'XYZ', timeframe, chart: pane.chart, candleSeriesRef, containerRef: createRef(), barsRevision: 1 };
}

function SceneProbe() {
  const scene = useAheadSceneOf('XYZ');
  return <span data-testid="probe">{scene ? `${scene.on}|${scene.anchorT}|${scene.words.join('/')}` : 'none'}</span>;
}

beforeEach(() => {
  localStorage.clear();
  reloadAheadPrefsForTesting();
  asked.mockClear();
});

afterEach(() => cleanup());

describe('AheadChartLayer', () => {
  it('asks nothing and draws nothing while the switch is off', () => {
    const pane = fakePane();
    render(<AheadChartLayer {...props(pane)} />);
    expect(asked).toHaveBeenCalledWith('XYZ', false);
    expect(asked).not.toHaveBeenCalledWith('XYZ', true);
    expect(pane.attached).toHaveLength(0);
  });

  it('draws on the 1-minute pane, hung on the newest completed candle, and publishes its scene', () => {
    const pane = fakePane();
    act(() => setAheadPrefs({ shown: true }));
    render(<><AheadChartLayer {...props(pane)} /><SceneProbe /></>);
    expect(asked).toHaveBeenLastCalledWith('XYZ', true);
    expect(pane.attached).toHaveLength(1);
    const [on, anchor, words] = screen.getByTestId('probe').textContent!.split('|');
    expect(on).toBe('true');
    // The forming candle is not the anchor: the newest one whose minute has ended is.
    expect(Number(anchor)).toBe(pane.data[9].time);
    expect(words).toContain(AHEAD_WORDS.readLoading);
  });

  it("adds what the zone's marks mean to the pane's Key while it draws, and takes it back when switched off", () => {
    const pane = fakePane();
    act(() => setAheadPrefs({ shown: true }));
    const view = render(<AheadChartLayer {...props(pane)} />);
    const [section] = paneKeySections(pane.chart);
    expect(section.title).toBe(AHEAD_KEY_TITLE);
    expect(section.rows.map(r => r.swatch)).toEqual(['dash', 'hatch']);
    view.unmount();
    expect(paneKeySections(pane.chart)).toEqual([]);
  });

  it('never asks or draws on another pane', () => {
    const pane = fakePane();
    act(() => setAheadPrefs({ shown: true }));
    render(<><AheadChartLayer {...props(pane, '5Min')} /><SceneProbe /></>);
    expect(asked).not.toHaveBeenCalledWith('XYZ', true);
    expect(pane.attached).toHaveLength(0);
    expect(screen.getByTestId('probe').textContent).toBe('none');
  });
});

describe('recentVolumes', () => {
  it("keeps the last completed minutes' real volumes, the forming one left out", () => {
    const minute = 29_875_000;
    const vol = fakePane(minute).data.map((b, i) => ({ time: b.time, value: 1000 + i }));
    const series = { data: () => vol } as unknown as ISeriesApi<'Histogram'>;
    expect(recentVolumes(series, minute)).toEqual(vol.slice(0, 10).map(v => v.value));
    expect(recentVolumes(null, minute)).toEqual([]);
  });
});

describe('completedCandles', () => {
  it('keeps the candles whose minute had ended by the desk clock', () => {
    const minute = 29_875_000;
    const pane = fakePane(minute);
    const out = completedCandles(pane.series as unknown as ISeriesApi<'Candlestick'>, minute);
    expect(out).toHaveLength(10);
    expect(out.at(-1)).toEqual({ t: pane.data[9].time, c: 5.09 });
    expect(completedCandles(null, minute)).toEqual([]);
    expect(completedCandles(pane.series as unknown as ISeriesApi<'Candlestick'>, null)).toEqual([]);
  });
});

describe('hasRoom', () => {
  it('needs two steps past the newest candle on screen', () => {
    expect(hasRoom({ from: 0, to: 12 } as never, 10)).toBe(true);
    expect(hasRoom({ from: 0, to: 11 } as never, 10)).toBe(false);
    expect(hasRoom(null, 10)).toBe(true);
  });
});
