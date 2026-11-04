/**
 * @vitest-environment jsdom
 *
 * RIOX 2026-11-04: the 10-second pane held tape-built bars and no IBKR history. It has no poll, and its retry ran
 * only while it had no bars, so after the one fill it asked for was shed nothing asked again: no history for good.
 * A pane whose `/bars` coverage says `history_pending` keeps asking until the history lands, then stops.
 */
import { renderHook, waitFor } from '@testing-library/react';
import type { CandlestickData, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: 'live' }) }));
vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: 'live' }) }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ discoveryProvider: 'ibkr' }) }));
vi.mock('../sim/useSimReplayTarget', () => ({ useSimReplayTarget: () => ({ target: null }) }));
vi.mock('../constants', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../constants')>()),
  CHART_BARS_STUCK_RETRY_MIN_MS: 20,
  CHART_BARS_STUCK_RETRY_MAX_MS: 40,
}));

import { clearBarsStoreForTests } from './barsStore';
import { useChartBars } from './useChartBars';

const TAPE_BAR = { t: '2026-11-04T13:32:00Z', o: 13.7, h: 13.7, l: 13.7, c: 13.7, v: 500 };
const HISTORY = Array.from({ length: 120 }, (_, i) => ({
  t: new Date(Date.parse('2026-11-04T13:12:00Z') + i * 10_000).toISOString(),
  o: 13.5, h: 13.8, l: 13.4, c: 13.7, v: 300,
}));

let historyLanded = false;
const fetchMock = vi.fn(async () => ({
  ok: true,
  json: async () => (historyLanded
    ? { bars: HISTORY, coverage: { as_of: HISTORY.at(-1)!.t, filling: false } }
    : { bars: [TAPE_BAR], coverage: { as_of: TAPE_BAR.t, filling: true, history_pending: true } }),
}));

function props() {
  const noop = () => {};
  const series = { setData: noop, update: noop };
  return {
    symbol: 'RIOX',
    timeframe: '10Sec',
    chartRef: { current: null as IChartApi | null },
    candleSeriesRef: { current: series as unknown as ISeriesApi<'Candlestick'> },
    volSeriesRef: { current: series as unknown as ISeriesApi<'Histogram'> },
    lastCandleRef: { current: null as CandlestickData<Time> | null },
    lastTrade: null,
    restoreAfterStorePaint: noop,
    onSeriesReset: noop,
    chartActive: true,
  };
}

beforeEach(() => {
  historyLanded = false;
  fetchMock.mockClear();
  clearBarsStoreForTests();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearBarsStoreForTests();
});

describe('useChartBars while its history is pending', () => {
  it('keeps asking a pane painted only by the tape, and stops once the history lands', async () => {
    const hook = renderHook((p: ReturnType<typeof props>) => useChartBars(p), { initialProps: props() });
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(1));
    expect(hook.result.current.filling).toBe(true);
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3));

    historyLanded = true;
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(HISTORY.length));
    await waitFor(() => expect(hook.result.current.filling).toBe(false));
    const asked = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(fetchMock.mock.calls.length).toBe(asked);
    hook.unmount();
  });
});
