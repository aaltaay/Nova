/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { MismatchDirection, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IndicatorBar } from '../chartIndicators';
import type { CandleHover } from './useCandleHover';

const state = vi.hoisted(() => ({ hover: null as CandleHover | null, priorClose: 1.89 as number | null }));
vi.mock('./useCandleHover', () => ({ useCandleHover: () => state.hover }));
vi.mock('../hooks/useTickerStream', () => ({
  useTickerSelect: (symbol: string | null) => (symbol ? state.priorClose : null),
}));

import { CandleHoverTip } from './CandleHoverTip';

const et = (h: number, m: number, day = 12) => Date.UTC(2026, 9, day, h, m) / 1000;

/** 9:20 to 9:41, each candle 100K shares, the 9:30 minute opening at $1.95 and the 9:41 candle 400K. */
function minuteBars(): IndicatorBar[] {
  const out: IndicatorBar[] = [];
  for (let m = 20; m <= 41; m += 1) {
    const open = m === 30 ? 1.95 : 2;
    out.push({ time: et(9, m), open, high: 2.1, low: 1.9, close: 2, volume: 100_000 });
  }
  out[out.length - 1] = { time: et(9, 41), open: 2.81, high: 3.05, low: 2.78, close: 3, volume: 400_000 };
  return out;
}

function fakeSeries<T>(rows: T[]) {
  return {
    dataByIndex: (index: number, dir?: MismatchDirection) => {
      if (index >= rows.length && dir === MismatchDirection.NearestLeft) return rows[rows.length - 1];
      return rows[index] ?? null;
    },
  };
}

function mount(timeframe = '1Min', bars = minuteBars(), hovered = bars.length - 1) {
  const candles = bars.map(b => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close }));
  const volumes = bars.map(b => ({ time: b.time as Time, value: b.volume }));
  const chart = {
    timeScale: () => ({
      logicalToCoordinate: (l: number) => l * 10,
      options: () => ({ barSpacing: 10 }),
      height: () => 28,
      width: () => 900,
    }),
  } as unknown as IChartApi;
  state.hover = { logical: hovered, time: bars[hovered].time as Time, x: 210, y: 120, width: 1000, height: 500 };
  return render(
    <CandleHoverTip
      chart={chart}
      candleSeriesRef={{ current: fakeSeries(candles) as unknown as ISeriesApi<'Candlestick'> }}
      volSeriesRef={{ current: fakeSeries(volumes) as unknown as ISeriesApi<'Histogram'> }}
      containerRef={{ current: document.createElement('div') }}
      symbol="SMPL"
      timeframe={timeframe}
      paneBars={bars}
      vwapSource={{ bars, revision: 1, coversOpen: false }}
    />,
  );
}

describe('CandleHoverTip', () => {
  beforeEach(() => {
    state.hover = null;
    state.priorClose = 1.89;
  });
  afterEach(cleanup);

  it('shows nothing until a candle is hovered', () => {
    state.hover = null;
    const { container } = render(
      <CandleHoverTip
        chart={null}
        candleSeriesRef={{ current: null }}
        volSeriesRef={{ current: null }}
        containerRef={{ current: null }}
        symbol="SMPL"
        timeframe="1Min"
        paneBars={[]}
        vwapSource={{ bars: [], revision: 0, coversOpen: false }}
      />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('names the candle: its time, session, move, prices, volume and where it closed', () => {
    mount();
    const tip = screen.getByTestId('candle-hover-tip');
    expect(tip.textContent).toContain('9:41 AM – 9:42 AM');
    expect(tip.textContent).toContain('Oct 12 · 1 min');
    expect(screen.getByText('Regular hours')).toBeTruthy();
    expect(screen.getByText('+6.76%')).toBeTruthy();
    expect(tip.textContent).toContain('+$0.19 open → close');
    expect(tip.textContent).toContain('Open$2.81');
    expect(tip.textContent).toContain('High$3.05');
    expect(tip.textContent).toContain('Low$2.78');
    expect(tip.textContent).toContain('Close$3.00');
    expect(screen.getByText('top 19%')).toBeTruthy();
    expect(screen.getByText('vs last 20 candles (avg 100.0K)')).toBeTruthy();
    expect(screen.getByText('4.0×')).toBeTruthy();
    expect(screen.getByText('≈ $1.2M')).toBeTruthy();
    // The bars start at 9:20, after 04:00: the day's total and its VWAP say so.
    expect(screen.getByText('Day volume by this candle (partial)')).toBeTruthy();
    expect(screen.getByText('2.5M')).toBeTruthy();
    expect(screen.getByText('vs prior close $1.89')).toBeTruthy();
    expect(screen.getByText('+58.73%')).toBeTruthy();
    expect(screen.getByText(/^vs VWAP \$.* \(partial\)$/)).toBeTruthy();
    expect(screen.getByText('vs 9:30 open $1.95')).toBeTruthy();
  });

  it('leaves out the prior close when the ticker has none', () => {
    state.priorClose = null;
    mount();
    expect(screen.queryByText(/vs prior close/)).toBeNull();
  });

  it('does not measure an older day\'s candle from today\'s prior close', () => {
    const bars = minuteBars();
    bars.push({ time: et(4, 0, 13), open: 3, high: 3, low: 3, close: 3, volume: 10 });
    mount('1Min', bars, bars.length - 2);
    expect(screen.getByText('vs 9:30 open $1.95')).toBeTruthy();
    expect(screen.queryByText(/vs prior close/)).toBeNull();
  });

  it('measures a daily candle from the day before, with no session or intraday rows', () => {
    const day = (d: number) => Date.UTC(2026, 9, d) / 1000;
    const bars: IndicatorBar[] = [
      { time: day(9), open: 1.5, high: 2, low: 1.4, close: 1.89, volume: 1e6 },
      { time: day(12), open: 1.95, high: 3.2, low: 1.9, close: 3, volume: 2e7 },
    ];
    mount('1Day', bars);
    const tip = screen.getByTestId('candle-hover-tip');
    expect(tip.textContent).toContain('Oct 12');
    expect(screen.getByText('vs prior close $1.89')).toBeTruthy();
    expect(screen.queryByText('Regular hours')).toBeNull();
    expect(screen.queryByText(/VWAP/)).toBeNull();
    expect(screen.queryByText(/9:30 open/)).toBeNull();
  });
});
