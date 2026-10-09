/**
 * @vitest-environment jsdom
 *
 * Operator report (2026-10-09): on Sim at the live edge the Trader's charts
 * read "Loading…" and never drew. The pane took every Sim tab for a replay, so
 * the live bars the backend serves at the edge were thrown away; and a refresh
 * that overtook the first load left that load's "Loading…" with nothing to
 * clear it.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import type { CandlestickData, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RawBar } from '../tickerChartData';

const clock = vi.hoisted(() => ({
  data: null as null | { live_edge?: boolean },
  listeners: new Set<() => void>(),
}));

vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: 'sim' }) }));
vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: 'sim' }) }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ discoveryProvider: 'ibkr' }) }));
vi.mock('../sim/useSimReplayTarget', () => ({ useSimReplayTarget: () => ({ target: { kind: 'ok' } }) }));
vi.mock('../sim', () => ({
  simClockResource: {
    getSnapshot: () => ({ data: clock.data, error: null }),
    subscribe: (listener: () => void) => {
      clock.listeners.add(listener);
      return () => { clock.listeners.delete(listener); };
    },
  },
}));

import { SIM_CHART_REFRESH_MS } from '../sim/simClockEvents';
import { CHART_EMPTY_REPLAY_TIME } from './chartBarsPolicy';
import { clearBarsStoreForTests } from './barsStore';
import { useChartBars } from './useChartBars';

const LIVE: RawBar[] = Array.from({ length: 5 }, (_, i) => ({
  t: new Date(Date.parse('2026-10-09T21:00:00Z') + i * 60_000).toISOString(), o: 9, h: 9.1, l: 8.9, c: 9.05, v: 100,
}));
const liveAnswer = () => ({ ok: true, json: async () => ({ bars: LIVE, coverage: { filling: false } }) });

function props() {
  const noop = () => {};
  const series = { setData: noop, update: noop };
  return {
    symbol: 'WFF',
    timeframe: '1Min',
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

/** Props made once: fresh callbacks every render would re-run the hook's effects for ever. */
function mount() {
  return renderHook((p: ReturnType<typeof props>) => useChartBars(p), { initialProps: props() });
}

function setClock(data: { live_edge?: boolean } | null) {
  clock.data = data;
  clock.listeners.forEach(listener => listener());
}

beforeEach(() => {
  clearBarsStoreForTests();
  clock.data = null;
  vi.stubGlobal('fetch', vi.fn(async () => liveAnswer()));
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearBarsStoreForTests();
  clock.listeners.clear();
});

describe('a Sim pane at the live edge', () => {
  it('draws the live bars', async () => {
    clock.data = { live_edge: true };
    const hook = mount();
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(5));
    expect(hook.result.current.loading).toBe(false);
    expect(hook.result.current.error).toBeNull();
    hook.unmount();
  });

  it('fetches again and draws when the clock first says the playhead is at the edge', async () => {
    const hook = mount();
    // No clock yet: the pane waits for it rather than paint live over a replay.
    await waitFor(() => expect(hook.result.current.loading).toBe(false));
    expect(hook.result.current.indicatorBars).toHaveLength(0);

    act(() => setClock({ live_edge: true }));
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(5));
    hook.unmount();
  });
});

describe('a refresh that overtakes the first load', () => {
  it('ends that load: the pane states its absence instead of "Loading…" for good', async () => {
    clock.data = { live_edge: false };
    const answers: Array<(value: unknown) => void> = [];
    vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { answers.push(resolve); }));
    const hook = mount();
    await waitFor(() => expect(hook.result.current.loading).toBe(true));

    // The replay's refresh clock fires while the first load is still out, and
    // joins that request: the refresh is now the pane's newest one.
    await act(async () => { await new Promise(r => setTimeout(r, SIM_CHART_REFRESH_MS + 100)); });
    await act(async () => {
      answers.forEach(answer => answer({
        ok: true,
        json: async () => ({ bars: [], coverage: { replay: true, replay_mode: 'completed_bars' } }),
      }));
    });

    await waitFor(() => expect(hook.result.current.loading).toBe(false));
    expect(hook.result.current.emptyText).toBe(CHART_EMPTY_REPLAY_TIME);
    hook.unmount();
  });
});
