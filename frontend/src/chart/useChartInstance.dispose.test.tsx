/**
 * @vitest-environment jsdom
 *
 * QA V19 / R30: uncaught "Object is disposed" page errors on Trader open (dev
 * StrictMode), tab close, pop-out, MACD toggle and replay seek. Two paths:
 * a resize queued before chart.remove(), and overlays below the pane calling
 * removeSeries on a chart the pane had already removed (React destroys a
 * parent's effects before its children's), which queued a redraw into
 * disposed canvases.
 */
import { act, StrictMode, useEffect, useRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { IChartApi } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type FakeChart = {
  removed: boolean;
  applyOptions: ReturnType<typeof vi.fn>;
  removeSeries: ReturnType<typeof vi.fn>;
};
const charts: FakeChart[] = [];

vi.mock('lightweight-charts', async (importOriginal) => ({
  ...(await importOriginal<typeof import('lightweight-charts')>()),
  createChart: vi.fn(() => {
    const guard = () => {
      if (chart.removed) throw new Error('Object is disposed');
    };
    const chart = {
      removed: false,
      applyOptions: vi.fn(guard),
      removeSeries: vi.fn(guard),
      addSeries: vi.fn(() => ({ setData: vi.fn() })),
      priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
      remove: vi.fn(() => {
        chart.removed = true;
      }),
    };
    charts.push(chart);
    return chart;
  }),
}));

import { useChartInstance } from './useChartInstance';

/** An overlay like TickerChartOverlays: adds a series, removes it on cleanup. */
function Overlay({ chart }: { chart: IChartApi | null }) {
  useEffect(() => {
    if (!chart) return undefined;
    const series = chart.addSeries({} as never);
    return () => chart.removeSeries(series);
  }, [chart]);
  return null;
}

function Harness({ height, withOverlay = false }: { height: number; withOverlay?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volSeriesRef = useRef(null);
  const chart = useChartInstance({
    containerRef,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    chartHeight: height,
    fillParentHeight: false,
    maximized: false,
  });
  return (
    <div ref={containerRef}>
      {withOverlay ? <Overlay chart={chart} /> : null}
    </div>
  );
}

describe('useChartInstance disposal (QA V19, R30)', () => {
  let container: HTMLDivElement;
  let root: Root;
  let frames: Map<number, FrameRequestCallback>;
  let nextFrame: number;
  const errors: unknown[] = [];

  beforeEach(() => {
    charts.length = 0;
    errors.length = 0;
    frames = new Map();
    nextFrame = 1;
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      const id = nextFrame++;
      frames.set(id, cb);
      return id;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      frames.delete(id);
    });
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    });
    vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => { errors.push(args); });
    window.addEventListener('error', onError);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    window.removeEventListener('error', onError);
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function onError(event: ErrorEvent) {
    errors.push(event.error);
    event.preventDefault();
  }

  function flushFrames() {
    const pending = [...frames.values()];
    frames.clear();
    for (const cb of pending) cb(0);
  }

  it('StrictMode mount -> cleanup -> mount: the first chart is never resized after removal (Trader open)', async () => {
    // The dev server runs StrictMode: the container ref stays set while the
    // first chart is removed, so its queued first-frame resize used to reach
    // the disposed canvas -- one uncaught error per pane on every Trader open.
    await act(async () => root.render(<StrictMode><Harness height={200} /></StrictMode>));
    expect(charts.length).toBeGreaterThanOrEqual(2);
    expect(charts[0].removed).toBe(true);
    expect(() => flushFrames()).not.toThrow();
    // The live chart still gets its first-frame size.
    expect(charts[charts.length - 1].applyOptions).toHaveBeenCalled();
    await act(async () => root.unmount());
  });

  it('overlays tidy up against a live chart; the pane is removed after them (tab close)', async () => {
    await act(async () => root.render(<Harness height={200} withOverlay />));
    await act(async () => root.unmount());
    const chart = charts[charts.length - 1];
    expect(chart.removeSeries).toHaveBeenCalledTimes(1);
    expect(chart.removed).toBe(true);
    expect(errors).toEqual([]);
    expect(() => flushFrames()).not.toThrow();
  });

  it('never resizes a chart that was removed before its first frame', async () => {
    await act(async () => root.render(<Harness height={200} />));
    await act(async () => root.unmount());
    expect(charts[0].removed).toBe(true);
    expect(() => flushFrames()).not.toThrow();
  });

  it('a layout change right before unmount does not resize the removed chart', async () => {
    await act(async () => root.render(<Harness height={200} />));
    await act(async () => root.render(<Harness height={320} />));
    await act(async () => root.unmount());
    const calls = charts[0].applyOptions.mock.calls.length;
    expect(() => flushFrames()).not.toThrow();
    expect(charts[0].applyOptions.mock.calls.length).toBe(calls);
  });
});
