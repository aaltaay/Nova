/**
 * @vitest-environment jsdom
 *
 * Operator ask (2026-09-23): switching Paper / Live / Sim must not zoom or pan
 * the chart. A switch into or out of Sim re-sources the pane (the live store's
 * bars <-> the replay's), and that repaint read as a first paint -- the
 * operator's window snapped back to the default one.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import type { CandlestickData, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RawBar } from '../tickerChartData';

const desk = vi.hoisted(() => ({ mode: 'live' as 'live' | 'paper' | 'sim' }));

vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: desk.mode }) }));
vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: desk.mode }) }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ discoveryProvider: 'ibkr' }) }));
vi.mock('../sim/useSimReplayTarget', () => ({ useSimReplayTarget: () => ({ target: null }) }));

import { isoToEtTime } from '../tickerChartData';
import { emitSimClockScrub } from '../sim/simClockEvents';
import { clearBarsStoreForTests } from './barsStore';
import { useChartBars } from './useChartBars';

type Range = { from: number; to: number };
type Command = { kind: 'fit' } | { kind: 'logical'; range: Range } | { kind: 'time'; range: Range };

const START_MS = Date.parse('2026-09-23T08:00:00Z');
const bars = (count: number): RawBar[] => Array.from({ length: count }, (_, i) => ({
  t: new Date(START_MS + i * 300_000).toISOString(), o: 10, h: 11, l: 9, c: 10.5, v: 100,
}));
/** The live store holds more history than a Sim replay of the same day. */
const LIVE = bars(200);
const REPLAY = LIVE.slice(50);
const etSec = (bar: RawBar) => isoToEtTime(bar.t, false) as number;

/** A time scale that reports what was last set and forgets it when the series is cleared. */
function fakePane() {
  const view: { logical: Range | null; time: Range | null } = { logical: null, time: null };
  const commands: Command[] = [];
  const timeScale = {
    fitContent: () => { commands.push({ kind: 'fit' }); },
    setVisibleLogicalRange: (range: Range) => {
      view.logical = { ...range };
      commands.push({ kind: 'logical', range: { ...range } });
    },
    setVisibleRange: (range: Range) => {
      view.time = { ...range };
      commands.push({ kind: 'time', range: { ...range } });
    },
    getVisibleLogicalRange: () => view.logical,
    getVisibleRange: () => view.time,
  };
  const series = () => ({
    setData: (data: unknown[]) => {
      if (data.length === 0) { view.logical = null; view.time = null; }
    },
    update: () => {},
  });
  const noop = () => {};
  const props = {
    symbol: 'ABC',
    timeframe: '5Min',
    chartRef: { current: { timeScale: () => timeScale } as unknown as IChartApi },
    candleSeriesRef: { current: series() as unknown as ISeriesApi<'Candlestick'> },
    volSeriesRef: { current: series() as unknown as ISeriesApi<'Histogram'> },
    lastCandleRef: { current: null as CandlestickData<Time> | null },
    lastTrade: null,
    applyLiveTrade: noop,
    onSeriesReset: noop,
    chartActive: true,
  };
  /** The operator zooms or pans. */
  const look = (logical: Range, time: Range | null = null) => {
    view.logical = logical;
    view.time = time;
  };
  return { props, commands, look, last: () => commands[commands.length - 1] };
}

function mount(pane: ReturnType<typeof fakePane>) {
  return renderHook((p: typeof pane.props) => useChartBars(p), { initialProps: pane.props });
}

beforeEach(() => {
  desk.mode = 'live';
  clearBarsStoreForTests();
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => (desk.mode === 'sim'
      ? { bars: REPLAY, coverage: { replay: true, replay_mode: 'completed_bars' } }
      : { bars: LIVE, coverage: { filling: false } }),
  })));
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearBarsStoreForTests();
});

describe('a venue switch keeps the chart where the operator left it', () => {
  it('Live -> Sim keeps the zoom following the tip', async () => {
    const pane = fakePane();
    const hook = mount(pane);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));
    // First paint: the default 5Min window.
    expect(pane.last()).toEqual({ kind: 'logical', range: { from: 104, to: 199 } });

    pane.look({ from: 170, to: 201 });
    desk.mode = 'sim';
    hook.rerender(pane.props);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(150));

    // Same 31-bar span and 2-bar right margin, on the replay's tip -- not the
    // default { from: 54, to: 149 }.
    expect(pane.last()).toEqual({ kind: 'logical', range: { from: 120, to: 151 } });
    expect(pane.commands).not.toContainEqual({ kind: 'fit' });
    hook.unmount();
  });

  it('Sim -> Live restores a window the operator panned back to', async () => {
    desk.mode = 'sim';
    const pane = fakePane();
    const hook = mount(pane);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(150));

    const window = { from: etSec(LIVE[80]), to: etSec(LIVE[110]) };
    pane.look({ from: 30, to: 60 }, window);
    desk.mode = 'live';
    hook.rerender(pane.props);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));

    expect(pane.last()).toEqual({ kind: 'time', range: window });
    hook.unmount();
  });

  it('Live -> Sim -> Live round-trips the same window', async () => {
    const pane = fakePane();
    const hook = mount(pane);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));

    const window = { from: etSec(LIVE[120]), to: etSec(LIVE[140]) };
    pane.look({ from: 120, to: 140 }, window);
    desk.mode = 'sim';
    hook.rerender(pane.props);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(150));
    expect(pane.last()).toEqual({ kind: 'time', range: window });

    desk.mode = 'live';
    hook.rerender(pane.props);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));
    expect(pane.last()).toEqual({ kind: 'time', range: window });
    hook.unmount();
  });

  it('a hidden Trader tab coming back keeps its window', async () => {
    const pane = fakePane();
    const hook = mount(pane);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));

    pane.look({ from: 170, to: 201 });
    hook.rerender({ ...pane.props, chartActive: false });
    const painted = pane.commands.length;
    hook.rerender({ ...pane.props, chartActive: true });
    await waitFor(() => expect(pane.commands.length).toBeGreaterThan(painted));
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));

    expect(pane.last()).toEqual({ kind: 'logical', range: { from: 170, to: 201 } });
    hook.unmount();
  });

  it('a Sim seek still refits: the time window genuinely moved', async () => {
    desk.mode = 'sim';
    const pane = fakePane();
    const hook = mount(pane);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(150));

    pane.look({ from: 120, to: 151 });
    const painted = pane.commands.length;
    act(() => emitSimClockScrub({ symbol: 'ABC' }));
    await waitFor(() => expect(pane.commands.length).toBeGreaterThan(painted));
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(150));

    expect(pane.last()).toEqual({ kind: 'logical', range: { from: 54, to: 149 } });
    hook.unmount();
  });

  it('a new symbol refits', async () => {
    const pane = fakePane();
    const hook = mount(pane);
    await waitFor(() => expect(hook.result.current.indicatorBars).toHaveLength(200));

    pane.look({ from: 170, to: 201 });
    const painted = pane.commands.length;
    hook.rerender({ ...pane.props, symbol: 'XYZ' });
    await waitFor(() => expect(pane.commands.length).toBeGreaterThan(painted));

    expect(pane.last()).toEqual({ kind: 'logical', range: { from: 104, to: 199 } });
    hook.unmount();
  });
});
