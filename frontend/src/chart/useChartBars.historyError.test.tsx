/**
 * @vitest-environment jsdom
 *
 * #555: the pane reads the backend's `last_error` from `/bars` coverage, so a
 * pane waiting on IBKR history can say IBKR is not answering.
 */
import { renderHook, waitFor } from '@testing-library/react';
import type { CandlestickData, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: 'live' }) }));
vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: 'live' }) }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ discoveryProvider: 'ibkr' }) }));
vi.mock('../sim/useSimReplayTarget', () => ({ useSimReplayTarget: () => ({ target: null }) }));

import { clearBarsStoreForTests } from './barsStore';
import { useChartBars } from './useChartBars';

const TIMEOUT = 'IBKR historical data did not answer within 20s';

function props(symbol: string) {
  const noop = () => {};
  const series = { setData: noop, update: noop };
  return {
    symbol,
    timeframe: '5Min',
    chartRef: { current: null as IChartApi | null },
    candleSeriesRef: { current: series as unknown as ISeriesApi<'Candlestick'> },
    volSeriesRef: { current: series as unknown as ISeriesApi<'Histogram'> },
    lastCandleRef: { current: null as CandlestickData<Time> | null },
    lastTrade: null,
    applyLiveTrade: noop,
    onSeriesReset: noop,
    chartActive: true,
  };
}

beforeEach(() => {
  clearBarsStoreForTests();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => ({
      bars: [],
      coverage: url.includes('/TLSA/')
        ? { filling: true, last_error: TIMEOUT, last_error_ts: 1_790_000_000 }
        : { filling: true, last_error: null, last_error_ts: null },
    }),
  })));
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearBarsStoreForTests();
});

describe('useChartBars history failure', () => {
  it('exposes the stated failure while the pane fills, and clears it for a quiet pane', async () => {
    const hook = renderHook((p: ReturnType<typeof props>) => useChartBars(p), {
      initialProps: props('TLSA'),
    });
    await waitFor(() => expect(hook.result.current.historyError).toBe(TIMEOUT));
    expect(hook.result.current.historyErrorTs).toBe(1_790_000_000);
    expect(hook.result.current.filling).toBe(true);

    hook.rerender(props('NNNN'));
    await waitFor(() => expect(hook.result.current.filling).toBe(true));
    await waitFor(() => expect(hook.result.current.historyError).toBeNull());
    expect(hook.result.current.historyErrorTs).toBeNull();
    hook.unmount();
  });
});
