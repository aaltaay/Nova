/** @vitest-environment jsdom */
import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { claimEdge, edgeContents } from '../chart/edgeWords';
import { CHART_EMA_COLORS, CHART_VWAP_COLOR } from '../constants';
import type { IndicatorBar } from '../chartIndicators';
import { TickerChartOverlays } from './TickerChartOverlays';

interface FakeSeries {
  opts: Record<string, unknown>;
  setData: ReturnType<typeof vi.fn>;
  applyOptions: (o: Record<string, unknown>) => void;
}

function fakeChart() {
  const made: FakeSeries[] = [];
  const chart = {
    addSeries: vi.fn((_kind: unknown, opts: Record<string, unknown>) => {
      const s: FakeSeries = { opts: { ...opts }, setData: vi.fn(), applyOptions: o => Object.assign(s.opts, o) };
      made.push(s);
      return s;
    }),
    removeSeries: vi.fn(),
  } as unknown as IChartApi;
  return { chart, made };
}

const OPEN = Date.parse('2026-09-30T13:30:00Z') / 1000;
const bars: IndicatorBar[] = Array.from({ length: 240 }, (_, i) => {
  const c = 5 + Math.sin(i / 9) * 0.3;
  return { time: OPEN + i * 60, open: c, high: c + 0.05, low: c - 0.05, close: c, volume: 1000 } as IndicatorBar;
});

function mount(chart: IChartApi) {
  return render(
    <TickerChartOverlays chart={chart} candleSeriesRef={{ current: null as ISeriesApi<'Candlestick'> | null }}
      symbol="LGHL" bars={bars} barsRevision={1} enabled={['emas', 'vwap']} timeframe="1Min"
      vwapSourceBars={bars} vwapSourceRevision={1} />,
  );
}

describe('TickerChartOverlays at the price pane\'s right edge', () => {
  it('keeps the EMAs out of the price scale: the candles decide what prices the pane shows', () => {
    const { chart, made } = fakeChart();
    mount(chart);
    const ema200 = made.find(s => s.opts.color === CHART_EMA_COLORS[200])!;
    const provider = ema200.opts.autoscaleInfoProvider as () => unknown;
    expect(provider()).toBeNull();
    const vwap = made.find(s => s.opts.color === CHART_VWAP_COLOR)!;
    expect(vwap.opts.autoscaleInfoProvider).toBeUndefined();
  });

  it('names its lines itself until a pane claims the edge, and then leaves the names to that pane', () => {
    const { chart, made } = fakeChart();
    mount(chart);
    const ema9 = made.find(s => s.opts.color === CHART_EMA_COLORS[9])!;
    const vwap = made.find(s => s.opts.color === CHART_VWAP_COLOR)!;
    expect(ema9.opts.title).toBe('9 EMA');
    expect(String(vwap.opts.title)).toMatch(/^VWAP/);
    expect(edgeContents(chart).words.map(w => w.id)).toEqual(['vwap', 'ema9', 'ema20', 'ema200']);
    expect(edgeContents(chart).words.find(w => w.id === 'ema9')).toMatchObject({ text: '9 EMA', valueWhenOff: true });

    let release = () => {};
    act(() => {
      release = claimEdge(chart);
    });
    expect(ema9.opts.title).toBe('');
    expect(vwap.opts.title).toBe('');
    act(() => release());
    expect(ema9.opts.title).toBe('9 EMA');
  });

  it('takes its words back when it goes', () => {
    const { chart } = fakeChart();
    const view = mount(chart);
    view.unmount();
    expect(edgeContents(chart).words).toEqual([]);
  });
});
