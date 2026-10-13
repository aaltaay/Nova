/**
 * @vitest-environment jsdom
 */
import { renderHook } from '@testing-library/react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrOrder, IbkrPosition } from '../ibkr/types';
import { isoToEtTime } from '../tickerChartData';
import { FillMarkersPrimitive } from './FillMarkersPrimitive';

let account: { positions: IbkrPosition[]; orders: IbkrOrder[]; closedOrders: IbkrOrder[] } | null = null;
vi.mock('../ibkr/IbkrAccountContext', () => ({ useOptionalIbkrAccountContext: () => account }));
let playhead: number | null = null;
vi.mock('../sim', () => ({ useSimReplayPlayhead: () => playhead }));

const { useChartPositionOverlay } = await import('./useChartPositionOverlay');

/** What every account poll hands over: the same rows, in new arrays and objects. */
function poll(avgCost = 2.76) {
  account = {
    positions: [{ symbol: 'AMOD', qty: 100, avg_cost: avgCost, market_price: null, market_value: null,
      unrealized_pnl: Math.random(), realized_pnl: null }],
    orders: [],
    closedOrders: [{ order_id: 7, symbol: 'AMOD', side: 'BUY', qty: 100, order_type: 'LMT', limit_price: 2.76,
      status: 'Filled', filled_qty: 100, avg_fill_price: 2.76, filled_at: '2026-10-02T13:30:10.000Z' }],
  };
}

function fakeSeries() {
  const attachPrimitive = vi.fn();
  const detachPrimitive = vi.fn();
  const createPriceLine = vi.fn(() => ({}));
  const removePriceLine = vi.fn();
  const series = { attachPrimitive, detachPrimitive, createPriceLine, removePriceLine };
  return { series: series as unknown as ISeriesApi<'Candlestick'>, attachPrimitive, detachPrimitive, createPriceLine, removePriceLine };
}

describe('useChartPositionOverlay', () => {
  const bars = [{ time: isoToEtTime('2026-10-02T13:30:00.000Z', false) as Time }];

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-02T15:00:00.000Z'));
    playhead = null;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('keeps one markers primitive and one price line across account polls', () => {
    const fake = fakeSeries();
    const chart = {} as IChartApi;
    const ref = { current: fake.series };
    poll();
    const { rerender } = renderHook(() => useChartPositionOverlay({
      chart, candleSeriesRef: ref, symbol: 'AMOD', timeframe: '1Min', bars, barsRevision: 1,
    }));
    for (let i = 0; i < 5; i += 1) {
      poll();
      rerender();
    }
    expect(fake.attachPrimitive).toHaveBeenCalledTimes(1);
    expect(fake.attachPrimitive.mock.calls[0][0]).toBeInstanceOf(FillMarkersPrimitive);
    expect(fake.detachPrimitive).not.toHaveBeenCalled();
    expect(fake.createPriceLine).toHaveBeenCalledTimes(1);
    expect(fake.removePriceLine).not.toHaveBeenCalled();
  });

  it('moves the price line when the average cost changes', () => {
    const fake = fakeSeries();
    const ref = { current: fake.series };
    poll(2.76);
    const { rerender } = renderHook(() => useChartPositionOverlay({
      chart: {} as IChartApi, candleSeriesRef: ref, symbol: 'AMOD', timeframe: '1Min', bars, barsRevision: 1,
    }));
    poll(2.9);
    rerender();
    expect(fake.createPriceLine).toHaveBeenCalledTimes(2);
    expect(fake.removePriceLine).toHaveBeenCalledTimes(1);
  });

  it("keeps a closed round trip's arrows after the position goes flat, with no cost line", () => {
    const setMarkers = vi.spyOn(FillMarkersPrimitive.prototype, 'setMarkers');
    const fake = fakeSeries();
    const ref = { current: fake.series };
    const minuteBars = [
      { time: isoToEtTime('2026-10-02T13:30:00.000Z', false) as Time },
      { time: isoToEtTime('2026-10-02T13:31:00.000Z', false) as Time },
    ];
    const chart = {} as IChartApi;
    poll();
    const { rerender } = renderHook(() => useChartPositionOverlay({
      chart, candleSeriesRef: ref, symbol: 'AMOD', timeframe: '1Min', bars: minuteBars, barsRevision: 1,
    }));
    // Flat: the sell closed the trade, and positions no longer list it.
    account = {
      positions: [],
      orders: [],
      closedOrders: [
        ...(account?.closedOrders ?? []),
        { order_id: 8, symbol: 'AMOD', side: 'SELL', qty: 100, order_type: 'LMT', limit_price: 2.9,
          status: 'Filled', filled_qty: 100, avg_fill_price: 2.9, filled_at: '2026-10-02T13:31:20.000Z' },
      ],
    };
    rerender();
    const drawn = setMarkers.mock.calls.at(-1)?.[0] ?? [];
    expect(drawn.map((m) => [m.shape, m.text])).toEqual([['arrowUp', '$2.76'], ['arrowDown', '$2.90']]);
    expect(fake.removePriceLine).toHaveBeenCalledTimes(1);
    // Polls of the same flat account draw nothing again.
    const calls = setMarkers.mock.calls.length;
    for (let i = 0; i < 3; i += 1) {
      account = { ...account, closedOrders: account.closedOrders.map((row) => ({ ...row })) };
      rerender();
    }
    expect(setMarkers).toHaveBeenCalledTimes(calls);
  });

  it('takes a fill off when a Sim rewind puts the playhead before it', () => {
    const setMarkers = vi.spyOn(FillMarkersPrimitive.prototype, 'setMarkers');
    const fake = fakeSeries();
    const ref = { current: fake.series };
    vi.setSystemTime(new Date('2026-10-13T15:00:00.000Z'));
    playhead = Date.parse('2026-10-02T13:35:00.000Z') / 1000;
    const chart = {} as IChartApi;
    poll();
    const { rerender } = renderHook(() => useChartPositionOverlay({
      chart, candleSeriesRef: ref, symbol: 'AMOD', timeframe: '1Min', bars, barsRevision: 1,
    }));
    expect(setMarkers.mock.calls.at(-1)?.[0]).toHaveLength(1);
    playhead = Date.parse('2026-10-02T13:30:00.000Z') / 1000;
    rerender();
    expect(setMarkers.mock.calls.at(-1)?.[0]).toEqual([]);
  });
});
