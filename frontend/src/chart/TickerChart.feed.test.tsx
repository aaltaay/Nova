/**
 * @vitest-environment jsdom
 *
 * The live pane still loads its own bars. A recorded feed paints the bars it was given and does not call the desk.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RawBar } from '../tickerChartData';

const painted: unknown[][] = [];

function fakeSeries() {
  return {
    setData: vi.fn((rows: unknown[]) => {
      painted.push(rows);
    }),
    update: vi.fn(),
    applyOptions: vi.fn(),
    createPriceLine: vi.fn(() => ({})),
    removePriceLine: vi.fn(),
    attachPrimitive: vi.fn(),
    detachPrimitive: vi.fn(),
    priceScale: () => ({ applyOptions: vi.fn() }),
    setMarkers: vi.fn(),
  };
}

function fakeChart() {
  const element = document.createElement('div');
  const chart = {
    applyOptions: vi.fn(),
    remove: vi.fn(),
    removeSeries: vi.fn(),
    addSeries: vi.fn(() => fakeSeries()),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    chartElement: () => element,
    timeScale: () => ({
      subscribeVisibleLogicalRangeChange: vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
      fitContent: vi.fn(),
      scrollToRealTime: vi.fn(),
      getVisibleLogicalRange: vi.fn(() => null),
      setVisibleLogicalRange: vi.fn(),
      applyOptions: vi.fn(),
    }),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
  };
  element.ownerDocument.body.appendChild(element);
  return chart;
}

vi.mock('lightweight-charts', async (importOriginal) => ({
  ...(await importOriginal<typeof import('lightweight-charts')>()),
  createChart: vi.fn(() => fakeChart()),
}));

vi.mock('lightweight-charts-drawing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lightweight-charts-drawing')>();
  return {
    ...actual,
    DrawingManager: class {
      attach() {}
      detach() {}
      setActiveTool() {}
      deselectAll() {}
      clearAll() {}
      importDrawings() {}
      addDrawing() {}
      removeDrawing() {}
      getAllDrawings() { return []; }
      getSelectedDrawing() { return null; }
      hitTestAnchor() { return null; }
      on() { return () => {}; }
    },
  };
});

vi.mock('../workspace', () => ({
  useWorkspace: () => ({ discoveryProvider: 'ibkr' }),
}));

vi.mock('./barsStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./barsStore')>();
  return {
    ...actual,
    ensureBars: vi.fn(async () => []),
    ensureBarsBatch: vi.fn(async () => undefined),
    getBarsEntry: vi.fn(() => null),
    isBarsEntryFresh: vi.fn(() => false),
    subscribeBars: vi.fn(() => () => {}),
  };
});

vi.mock('../ibkr/ibkrStatusPoller', () => {
  const snapshot = {
    enabled: false,
    connected: false,
    transport_connected: false,
    session_reason: 'disabled',
    mode: 'disconnected',
    orders_enabled: false,
    short_enabled: false,
    spend_status: 'locked',
    trading_allowed: false,
    trading_allowed_reason: '',
    market_data_type: null,
    market_data_delayed: false,
    clientReady: true,
    stale: false,
    staleSince: null,
  };
  return {
    DEFAULT_IBKR_STATUS: snapshot,
    getIbkrStatusSnapshot: () => snapshot,
    refreshIbkrStatusNow: vi.fn(),
    subscribeIbkrStatus: vi.fn(() => () => {}),
  };
});

import { ChartFeedProvider, type RecordedChartFeed } from './chartFeed';
import { TickerChart } from './TickerChart';
import { ensureBars } from './barsStore';
import { subscribeIbkrStatus } from '../ibkr/ibkrStatusPoller';
import { recordedBarsClosedBy } from './useRecordedBars';

const AS_OF = '2026-09-18T10:00:00-04:00';

function bar(clock: string, high: number): RawBar {
  return { t: `2026-09-18T${clock}-04:00`, o: 1, h: high, l: 0.5, c: high, v: 10 };
}

function recordedFeed(bars: RawBar[]): RecordedChartFeed {
  return {
    kind: 'recorded',
    symbol: 'IMCC',
    date: '2026-09-18',
    asOfIso: AS_OF,
    source: 'fixture',
    bars: { '1Min': bars },
    vwapBars: [bar('09:58:00', 2)],
  };
}

describe('recordedBarsClosedBy', () => {
  it('drops a bar whose window is still open at as_of', () => {
    const kept = recordedBarsClosedBy(
      [bar('09:59:00', 4), bar('10:00:00', 80)],
      '1Min',
      AS_OF,
    );
    expect(kept.map((row) => row.h)).toEqual([4]);
  });
});

describe('TickerChart feed', () => {
  let root: Root;
  let host: HTMLDivElement;
  const sockets: unknown[] = [];

  beforeEach(() => {
    painted.length = 0;
    sockets.length = 0;
    if (!globalThis.ResizeObserver) {
      globalThis.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
      } as unknown as typeof ResizeObserver;
    }
    vi.stubGlobal('WebSocket', class {
      constructor(...args: unknown[]) { sockets.push(args); }
      close() {}
      addEventListener() {}
      removeEventListener() {}
    });
    vi.spyOn(globalThis, 'fetch');
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('still asks for bars and subscribes to gateway status on the live feed', async () => {
    await act(async () => {
      root.render(<TickerChart symbol="SMPL" fixedTimeframe="5Min" />);
    });
    expect(ensureBars).toHaveBeenCalled();
    expect(vi.mocked(ensureBars).mock.calls.some((call) => call[1] === '5Min')).toBe(true);
    expect(subscribeIbkrStatus).toHaveBeenCalled();
  });

  it('paints the closed recorded bars and does not call the desk', async () => {
    const feed = recordedFeed([bar('09:58:00', 2), bar('09:59:00', 4), bar('10:00:00', 80)]);
    await act(async () => {
      root.render(
        <ChartFeedProvider feed={feed}>
          <TickerChart symbol="IMCC" fixedTimeframe="1Min" />
        </ChartFeedProvider>,
      );
    });
    const card = host.querySelector('[data-testid="ticker-chart-1Min"]');
    expect(card?.getAttribute('data-bar-count')).toBe('2');
    expect(painted.some((rows) => rows.length === 2)).toBe(true);
    expect(painted.some((rows) => rows.some((row) => JSON.stringify(row).includes('"high":80') || JSON.stringify(row).includes(':80')))).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
    expect(sockets).toEqual([]);
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    for (const banned of ['/api/ibkr', '/api/ticker', '/api/chart-drawings', '/api/orders', '/api/bot']) {
      expect(urls.some((url) => url.includes(banned))).toBe(false);
    }
    host.querySelector('.chart-body')?.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }));
    expect(host.textContent ?? '').not.toMatch(/Buy|Flatten|Allowlist/);
  });

  it('does not paint a recorded bar that ends after as_of', async () => {
    const feed = recordedFeed([bar('10:00:00', 80)]);
    await act(async () => {
      root.render(
        <ChartFeedProvider feed={feed}>
          <TickerChart symbol="IMCC" fixedTimeframe="1Min" />
        </ChartFeedProvider>,
      );
    });
    expect(host.querySelector('[data-testid="ticker-chart-1Min"]')?.getAttribute('data-bar-count')).toBe('0');
    expect(painted.some((rows) => rows.length > 0)).toBe(false);
  });
});
