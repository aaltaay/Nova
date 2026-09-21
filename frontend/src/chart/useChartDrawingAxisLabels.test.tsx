/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ISeriesApi } from 'lightweight-charts';
import { useChartDrawingAxisLabels } from './useChartDrawingAxisLabels';

const store = vi.hoisted(() => ({ drawings: [] as unknown[] }));
vi.mock('./chartDrawingsStore', () => ({
  drawingsKey: (s: string) => s.trim().toUpperCase(),
  getDrawings: () => store.drawings,
  subscribeDrawings: () => () => {},
}));

function fakeSeries() {
  const live = new Set<object>();
  const series = {
    createPriceLine: vi.fn(() => { const line = { applyOptions: vi.fn() }; live.add(line); return line; }),
    removePriceLine: vi.fn((line: object) => { live.delete(line); }),
  };
  return { series: series as unknown as ISeriesApi<'Candlestick'>, live };
}

const hline = (id: string, price: number) => ({
  id, type: 'horizontal-line', anchors: [{ price, time: 1 }], style: { lineColor: '#3b82f6' },
});

beforeEach(() => { store.drawings = [hline('h1', 8.11)]; });

describe('useChartDrawingAxisLabels', () => {
  it('keeps ONE chip per level while bars keep arriving (the duplicate-chip regression)', () => {
    const { series, live } = fakeSeries();
    const ref = { current: series };
    const { rerender } = renderHook(
      ({ rev }) => useChartDrawingAxisLabels({ candleSeriesRef: ref, symbol: 'IMCC', seriesRevision: rev }),
      { initialProps: { rev: 1 } },
    );
    // `barsRevision` moves on every new bar; it must not forget the live line.
    for (const rev of [2, 3, 4, 5]) rerender({ rev });
    expect(live.size).toBe(1);
  });

  it('rebuilds on a new series without touching the dead one', () => {
    const first = fakeSeries();
    const ref = { current: first.series };
    const { rerender } = renderHook(
      ({ rev }) => useChartDrawingAxisLabels({ candleSeriesRef: ref, symbol: 'IMCC', seriesRevision: rev }),
      { initialProps: { rev: 1 } },
    );
    const second = fakeSeries();
    ref.current = second.series;
    rerender({ rev: 2 });
    expect(second.live.size).toBe(1);
    expect(first.series.removePriceLine).not.toHaveBeenCalled();
  });

  it('removes its lines on unmount', () => {
    const { series, live } = fakeSeries();
    const { unmount } = renderHook(() => useChartDrawingAxisLabels({
      candleSeriesRef: { current: series }, symbol: 'IMCC', seriesRevision: 1,
    }));
    unmount();
    expect(live.size).toBe(0);
  });
});
