/**
 * @vitest-environment jsdom
 *
 * Operator report (2026-09-24, FOFO after hours): "i do not see a volume
 * coming up" on the forming 1-minute candle, and the same on 5 minutes. The
 * forming candle was drawn from live price ticks only, so its volume waited
 * for the bar store, which refreshes from IBKR history at most every ~45 s.
 * And every 30 s store refresh collapsed the forming candle to one price:
 * lightweight-charts refuses an update older than its newest bar, the pane
 * repainted from the store, and the tip was rebuilt from the last trade alone.
 */
import { act, renderHook } from '@testing-library/react';
import type {
  CandlestickData,
  HistogramData,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const desk = vi.hoisted(() => ({ mode: 'live' as 'live' | 'paper' | 'sim' }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: desk.mode }) }));
vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: desk.mode }) }));

import { clearEtOffsetCacheForTests, tradeBucket, type RawBar } from '../tickerChartData';
import { resetTickerStreamsForTests } from '../hooks/tickerStore';
import { CHART_10SEC_TAPE_OWNS_MS } from '../constants';
import { clearBarsStoreForTests, getBarsEntry, upsertTapePrint10SecBar } from './barsStore';
import { paintBars } from './chartBarsPaint';
import type { ChartTradeUpdate } from './types';
import { useChartLiveTrade } from './useChartLiveTrade';

type Point = { time: Time };

/** A series with lightweight-charts' rules: an update older than the newest bar throws. */
function fakeSeries<T extends Point>() {
  let data: T[] = [];
  const api = {
    setData: (next: T[]) => { data = [...next]; },
    update: (bar: T) => {
      const last = data.at(-1);
      if (last && (bar.time as number) < (last.time as number)) {
        throw new Error(`Cannot update oldest data, last time=${String(last.time)}, new time=${String(bar.time)}`);
      }
      if (last && last.time === bar.time) data[data.length - 1] = bar;
      else data.push(bar);
    },
  };
  return { api, data: () => data };
}

const timeScale = {
  fitContent: () => {},
  setVisibleLogicalRange: () => {},
  setVisibleRange: () => {},
  getVisibleLogicalRange: () => ({ from: 0, to: 10 }),
  getVisibleRange: () => null,
};

function setup(timeframe = '1Min', followTicker = false) {
  const candles = fakeSeries<CandlestickData<Time>>();
  const volumes = fakeSeries<HistogramData<Time>>();
  const candleSeriesRef = { current: candles.api as unknown as ISeriesApi<'Candlestick'> };
  const volSeriesRef = { current: volumes.api as unknown as ISeriesApi<'Histogram'> };
  const chartRef = { current: { timeScale: () => timeScale } as unknown as IChartApi };
  let renders = 0;
  const hook = renderHook(
    ({ trade }: { trade: ChartTradeUpdate | null }) => {
      renders += 1;
      return useChartLiveTrade(candleSeriesRef, volSeriesRef, followTicker ? undefined : trade, timeframe, 'FOFO',
        followTicker);
    },
    { initialProps: { trade: null as ChartTradeUpdate | null } },
  );
  let painted: RawBar[] | null = null;
  const epoch = { current: 0 };
  /** The store answers (the pane's 30 s refresh); the live tip goes back on top. */
  const storePaint = (bars: RawBar[]) => {
    act(() => {
      paintBars(
        bars, timeframe, candleSeriesRef, volSeriesRef, hook.result.current.lastCandleRef,
        chartRef, painted, epoch,
      );
      painted = bars;
      hook.result.current.restoreAfterStorePaint(bars.at(-1)?.v ?? null, null, timeframe);
    });
  };
  const trade = (iso: string, price: number, dayVolume: number | null) => {
    hook.rerender({ trade: { price, timestamp: iso, symbol: 'FOFO', dayVolume } });
  };
  return {
    storePaint,
    trade,
    renders: () => renders,
    tip: () => candles.data().at(-1),
    volumeAt: (iso: string) => volumes.data().find((v) => v.time === tradeBucket(iso, timeframe))?.value,
  };
}

const bar = (iso: string, o: number, h: number, l: number, c: number, v: number): RawBar =>
  ({ t: iso, o, h, l, c, v });

const STORE_THROUGH_2003 = [
  bar('2026-09-24T20:02:00Z', 2.7, 3.27, 2.65, 3.1001, 385_286),
  bar('2026-09-24T20:03:00Z', 3.12, 3.1273, 2.82, 2.96, 244_345),
];

describe('useChartLiveTrade -- the forming candle carries its volume', () => {
  beforeEach(() => {
    desk.mode = 'live';
    clearEtOffsetCacheForTests();
    clearBarsStoreForTests();
  });

  it('counts the forming bar from the day volume and keeps it across a store refresh', () => {
    const chart = setup();
    chart.storePaint(STORE_THROUGH_2003);
    // The first day volume seen is a baseline: 20:03 keeps the store's figure.
    chart.trade('2026-09-24T20:03:40Z', 2.96, 1_000_000);
    expect(chart.volumeAt('2026-09-24T20:03:00Z')).toBe(244_345);

    chart.trade('2026-09-24T20:04:02Z', 2.97, 1_010_000);
    chart.trade('2026-09-24T20:04:20Z', 3.14, 1_050_000);
    chart.trade('2026-09-24T20:04:28Z', 2.9, 1_080_000);
    chart.trade('2026-09-24T20:04:30Z', 3.05, 1_090_000);
    expect(chart.volumeAt('2026-09-24T20:04:30Z')).toBe(90_000);

    // The store still ends at 20:03: the refresh must not flatten 20:04.
    chart.storePaint([...STORE_THROUGH_2003]);
    expect(chart.tip()).toMatchObject({ open: 2.97, high: 3.14, low: 2.9, close: 3.05 });
    expect(chart.volumeAt('2026-09-24T20:04:30Z')).toBe(90_000);
  });

  it('merges a store bar for the forming minute and shows the larger count', () => {
    const chart = setup();
    chart.storePaint(STORE_THROUGH_2003);
    chart.trade('2026-09-24T20:03:50Z', 2.96, 1_000_000);
    chart.trade('2026-09-24T20:04:05Z', 2.97, 1_020_000);
    chart.trade('2026-09-24T20:04:40Z', 3.05, 1_095_000);

    // IBKR history caught the forming bar with more shares than Nova counted.
    chart.storePaint([
      ...STORE_THROUGH_2003,
      bar('2026-09-24T20:04:00Z', 2.97, 3.14, 2.9, 3.07, 120_000),
    ]);
    expect(chart.tip()).toMatchObject({ open: 2.97, high: 3.14, low: 2.9, close: 3.05 });
    expect(chart.volumeAt('2026-09-24T20:04:00Z')).toBe(120_000);

    // The next minute is counted from its own first trade.
    chart.trade('2026-09-24T20:05:01Z', 3.0, 1_100_000);
    expect(chart.volumeAt('2026-09-24T20:05:01Z')).toBe(5_000);
  });

  it('draws no volume for a bar whose start the chart did not see', () => {
    const chart = setup();
    chart.storePaint(STORE_THROUGH_2003);
    chart.trade('2026-09-24T20:04:10Z', 2.97, 1_000_000);
    chart.trade('2026-09-24T20:04:30Z', 3.05, 1_040_000);
    expect(chart.tip()).toMatchObject({ close: 3.05 });
    expect(chart.volumeAt('2026-09-24T20:04:00Z')).toBeUndefined();
  });

  it('counts a 5-minute bar the same way', () => {
    const chart = setup('5Min');
    chart.storePaint([bar('2026-09-24T20:00:00Z', 2.43, 3.27, 2.4, 3.07, 842_930)]);
    chart.trade('2026-09-24T20:04:50Z', 3.07, 2_000_000);
    chart.trade('2026-09-24T20:05:10Z', 3.07, 2_030_000);
    chart.trade('2026-09-24T20:07:30Z', 2.95, 2_211_000);
    expect(chart.volumeAt('2026-09-24T20:05:00Z')).toBe(211_000);
  });

  it('leaves 10-second volume to the tape', () => {
    const chart = setup('10Sec');
    chart.storePaint([bar('2026-09-24T20:04:00Z', 3, 3, 3, 3, 500)]);
    chart.trade('2026-09-24T20:04:05Z', 3.01, 1_000_000);
    chart.trade('2026-09-24T20:04:12Z', 3.02, 1_004_000);
    expect(chart.tip()).toMatchObject({ close: 3.02 });
    expect(chart.volumeAt('2026-09-24T20:04:12Z')).toBeUndefined();
  });
});

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  close() {
    this.readyState = 3;
    this.onclose?.({});
  }
  send() {}
}

describe('useChartLiveTrade -- following the ticker stream (#707)', () => {
  beforeEach(() => {
    desk.mode = 'live';
    clearEtOffsetCacheForTests();
    clearBarsStoreForTests();
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    resetTickerStreamsForTests();
    vi.unstubAllGlobals();
  });

  it('draws each print as it comes, with no render of the chart', () => {
    const chart = setup('1Min', true);
    chart.storePaint(STORE_THROUGH_2003);
    const ws = FakeWebSocket.instances[0];
    expect(ws.url).toContain('/ticker/FOFO');
    const send = (msg: object) => act(() => ws.onmessage?.({ data: JSON.stringify(msg) }));
    send({ type: 'initial', symbol: 'FOFO', snapshot: { latest_trade: { price: 2.96, timestamp: '2026-09-24T20:03:40Z' } } });
    const renders = chart.renders();

    send({ type: 'trade_update', symbol: 'FOFO', price: 2.97, timestamp: '2026-09-24T20:04:02Z', volume: 1_010_000 });
    send({ type: 'trade_update', symbol: 'FOFO', price: 3.14, timestamp: '2026-09-24T20:04:20Z', volume: 1_050_000 });
    send({ type: 'trade_update', symbol: 'FOFO', price: 3.05, timestamp: '2026-09-24T20:04:30Z', volume: 1_090_000 });
    expect(chart.tip()).toMatchObject({ open: 2.97, high: 3.14, close: 3.05 });
    // A new forming minute is the only render (its time is state); the prints inside it are none.
    expect(chart.renders()).toBeLessThanOrEqual(renders + 1);

    // A store refresh puts the live tip back, as with a passed trade.
    chart.storePaint([...STORE_THROUGH_2003]);
    expect(chart.tip()).toMatchObject({ open: 2.97, high: 3.14, low: 2.97, close: 3.05 });
  });
});

describe('useChartLiveTrade -- the 10-second pane has one writer (#721)', () => {
  // Operator report 2026-10-05: "two candles drawing together ... the previous candle should never move".
  // The tape keyed its candle by arrival while a Level 1 trade, stamped when its tick landed, opened the
  // next candle at the boundary: both candles moved at once.
  const sec = (iso: string) => Date.parse(iso) / 1000;
  const print = (iso: string, exchangeIso: string, price: number) => upsertTapePrint10SecBar('FOFO', {
    time: iso, price, size: 100, exchangeTs: sec(exchangeIso),
  });

  beforeEach(() => {
    clearBarsStoreForTests();
    clearEtOffsetCacheForTests();
    desk.mode = 'live';
  });

  afterEach(() => {
    clearBarsStoreForTests();
    vi.useRealTimers();
  });

  it("ignores the Level 1 last while the tape feeds the pane: no second candle opens", () => {
    const chart = setup('10Sec');
    print('2026-09-24T20:04:01.300Z', '2026-09-24T20:04:01Z', 3);
    print('2026-09-24T20:04:09.900Z', '2026-09-24T20:04:09Z', 3.02);
    chart.storePaint(getBarsEntry('FOFO', '10Sec')!.bars);
    chart.trade('2026-09-24T20:04:10.150Z', 3.02, 1_000_000);    // its Level 1 tick, past the boundary
    expect(chart.tip()).toMatchObject({ time: tradeBucket('2026-09-24T20:04:00Z', '10Sec'), close: 3.02 });
  });

  it('draws the Level 1 last when no tape feeds the pane', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-24T20:04:10Z'));
    const chart = setup('10Sec');
    print('2026-09-24T20:04:01.300Z', '2026-09-24T20:04:01Z', 3);
    chart.storePaint(getBarsEntry('FOFO', '10Sec')!.bars);
    vi.setSystemTime(Date.now() + CHART_10SEC_TAPE_OWNS_MS);     // the tape has said nothing since
    chart.trade('2026-09-24T20:04:26Z', 3.1, null);
    expect(chart.tip()).toMatchObject({ time: tradeBucket('2026-09-24T20:04:20Z', '10Sec'), close: 3.1 });
  });
});
