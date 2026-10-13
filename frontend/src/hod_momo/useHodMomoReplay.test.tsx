/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SimClockState } from '../sim/simClockTypes';
import { HodMomoContextProvider, type HodMomoContextValue } from './HodMomoContext';
import { HodMomoDock } from './HodMomoDock';
import type { AlertObject } from './types';
import { countRaisedBy, parseHodHistory, parseHodHistoryDay, sortByRaised, useHodMomoReplay } from './useHodMomoReplay';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), mode: 'sim' as string }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: mocks.mode }) }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ selectedSymbol: null, setSelectedSymbol: vi.fn(), selectRowSymbol: vi.fn(), openStockView: vi.fn() }),
}));
vi.mock('../sample_data/SampleDataContext', () => ({ useSampleDataOptional: () => null }));
vi.mock('./useHodMomoIntegrity', () => ({ useHodMomoIntegrity: () => ({ report: null, error: null, status: 'pass' }) }));
vi.mock('./HodMomoDebugPanel', () => ({ HodMomoDebugPanel: () => null }));
vi.mock('./HodMomoSettings', () => ({ HodMomoSettings: () => null }));

let clockState: { data: SimClockState | null; error: string | null } = { data: null, error: null };
const listeners = new Set<() => void>();
vi.mock('../sim/simClockResource', () => ({
  simClockResource: {
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => clockState,
  },
}));
const setClock = (time: string | null, over: Partial<SimClockState> = {}) => {
  clockState = {
    data: time ? {
      sim: true, live_edge: false, paused: true, session_date: '2026-09-21', sim_time_et: `2026-09-21T${time}-04:00`, ...over,
    } : null,
    error: null,
  };
  listeners.forEach(listener => listener());
};
const epoch = (time: string) => Date.parse(`2026-09-21T${time}-04:00`) / 1000;

const alert = (id: string, time: string, ticker = 'GRML'): AlertObject => ({
  id, ticker, timestamp: new Date((epoch(time) - 5) * 1000).toISOString(), created_ts: epoch(time),
  strategy_id: 7, strategy_name: 'Low Float - High Rel Vol', price: 9, change_pct: 30, rvol: 5, float_shares: null,
  gap_pct: null, volume: null, momentum_pct: null, rvol_source: null, consolidation_count: 1, consolidated_ids: [],
});
const HISTORY = [alert('a', '07:41:30'), alert('b', '07:42:30', 'QNME'), alert('c', '07:43:10', 'BRNQ')];
/** Days the mock backend holds no HOD Momo snapshot for (`recorded: false`). */
let unrecorded = new Set<string>();
const historyCalls = () => mocks.fetch.mock.calls.map(([url]) => String(url)).filter(url => url.includes('/api/hod-momo/history/'));

beforeEach(() => {
  mocks.mode = 'sim';
  listeners.clear();
  setClock(null);
  unrecorded = new Set();
  mocks.fetch.mockReset().mockImplementation(async (url: string) => {
    const parsed = new URL(url, 'http://x');
    const date = decodeURIComponent(parsed.pathname.split('/').pop() ?? '');
    const until = Number(parsed.searchParams.get('until'));
    const recorded = !unrecorded.has(date);
    const alerts = recorded ? HISTORY.filter(a => (a.created_ts ?? 0) <= until) : [];
    return { ok: true, status: 200, text: async () => JSON.stringify({ date, recorded, alerts, error: null }) };
  });
});
afterEach(() => cleanup());

describe('useHodMomoReplay', () => {
  it('is null on Live / Paper and at the live edge (the strip stays on the socket)', async () => {
    mocks.mode = 'live';
    setClock('07:42:10');
    const { result, rerender } = renderHook(() => useHodMomoReplay());
    await act(async () => {});
    expect(result.current).toBeNull();
    mocks.mode = 'sim';
    setClock('07:42:10', { live_edge: true });
    rerender();
    await act(async () => {});
    expect(result.current).toBeNull();
    expect(historyCalls()).toEqual([]);
  });

  it('shows only alerts raised at or before the playhead second, reading the history once a minute', async () => {
    setClock('07:42:10');
    const { result } = renderHook(() => useHodMomoReplay());
    await waitFor(() => expect(result.current?.state.loading).toBe(false));
    expect(historyCalls()).toHaveLength(1);
    expect(historyCalls()[0]).toContain(`/api/hod-momo/history/2026-09-21?until=${epoch('07:43:00')}`);
    expect(result.current?.alerts.map(a => a.id)).toEqual(['a']);

    await act(async () => { setClock('07:42:30'); });
    expect(result.current?.alerts.map(a => a.id)).toEqual(['b', 'a']);
    expect(historyCalls()).toHaveLength(1);

    await act(async () => { setClock('07:43:20'); });
    await waitFor(() => expect(result.current?.alerts.map(a => a.id)).toEqual(['c', 'b', 'a']));
    expect(historyCalls()).toHaveLength(2);

    // Scrubbing back hides what was raised after the new playhead at once.
    await act(async () => { setClock('07:41:40'); });
    expect(result.current?.alerts.map(a => a.id)).toEqual(['a']);
  });

  it('a day with no HOD Momo history reads as not recorded; a recorded day before its first alert as recorded', async () => {
    unrecorded = new Set(['2026-09-21']);
    setClock('07:20:10');
    const { result, rerender } = renderHook(() => useHodMomoReplay());
    await waitFor(() => expect(result.current?.state.loading).toBe(false));
    expect(result.current?.state.recorded).toBe(false);
    expect(result.current?.alerts).toEqual([]);

    unrecorded = new Set();
    await act(async () => { setClock('07:21:10'); });
    rerender();
    await waitFor(() => expect(result.current?.state.loading).toBe(false));
    expect(result.current?.state.recorded).toBe(true);
    expect(result.current?.alerts).toEqual([]);
  });

  it('an older backend bare list is read, but cannot say whether the day was recorded; an unreadable snapshot throws', () => {
    expect(parseHodHistoryDay([HISTORY[0]])).toEqual({ recorded: null, alerts: [HISTORY[0]] });
    expect(parseHodHistoryDay({ date: '2026-07-15', recorded: false, alerts: [], error: null }))
      .toEqual({ recorded: false, alerts: [] });
    expect(() => parseHodHistoryDay({ recorded: true, alerts: [], error: 'Nova holds HOD alert history for 2026-09-21 but could not read it.' }))
      .toThrow(/could not read it/);
  });

  it('reads the list and orders by the time Nova raised each alert; undated alerts are left out', () => {
    const undated = { ...alert('z', '07:00:00'), created_ts: undefined, timestamp: 'garbage' };
    const sorted = sortByRaised(parseHodHistory({ alerts: [HISTORY[2], HISTORY[0], undated] }));
    expect(sorted.map(a => a.id)).toEqual(['a', 'c']);
    expect(countRaisedBy(sorted, epoch('07:42:00'))).toBe(1);
    expect(countRaisedBy(sorted, null)).toBe(0);
  });
});

function contextValue(replay: HodMomoContextValue['replay'], alerts: AlertObject[]): HodMomoContextValue {
  return {
    stream: { alerts, totalToday: alerts.length, connected: true },
    config: {
      state: { loaded: true, strategies: {}, master: { consolidation_sec: 5 } } as unknown as HodMomoContextValue['config']['state'],
      updateStrategy: () => {}, updateMaster: () => {}, resetStrategy: async () => {}, resetAll: async () => {},
    },
    hodCount: alerts.length, runningUpCount: 0, dockMode: 'hod_momo', setDockMode: vi.fn(), collapsed: false,
    setCollapsed: vi.fn(), toggleCollapsed: vi.fn(), rows: 4, setRows: vi.fn(), focusDock: vi.fn(),
    showHodSettings: false, setShowHodSettings: vi.fn(), toggleHodSettings: vi.fn(), replay,
  };
}

describe('HodMomoDock at the Sim playhead', () => {
  const replay = { date: '2026-09-21', minute: epoch('07:42:00'), loading: false, error: null, recorded: true };

  it('Clear is disabled, the feed word names the replay, and past alerts are never NEW', () => {
    const { rerender } = render(
      <HodMomoContextProvider value={contextValue(replay, [HISTORY[0]])}><HodMomoDock /></HodMomoContextProvider>,
    );
    rerender(<HodMomoContextProvider value={contextValue(replay, [HISTORY[1], HISTORY[0]])}><HodMomoDock /></HodMomoContextProvider>);
    expect(screen.queryByText('NEW')).toBeNull();
    expect(screen.getByTestId('hod-momo-strip-feed').textContent).toBe('replay 07:42');
    fireEvent.click(screen.getByTestId('hod-momo-strip-more'));
    const clear = screen.getByTestId('hod-momo-dock-clear') as HTMLButtonElement;
    expect(clear.disabled).toBe(true);
    // The reason rides the locked-control tip (ux/whyTip.ts), not a native title.
    expect(clear.getAttribute('data-why')).toMatch(/nothing to clear/);
    expect(clear.title).toBe('');
  });

  it('an empty strip says no alert was raised by the playhead, not "No alerts yet"', () => {
    render(<HodMomoContextProvider value={contextValue(replay, [])}><HodMomoDock /></HodMomoContextProvider>);
    expect(screen.getByTestId('hod-momo-strip-empty').textContent).toBe('No alerts raised by 07:42 ET on 2026-09-21');
    expect(screen.getByTestId('hod-momo-strip-since').textContent).toBe('0 alerts');
    expect(screen.getByTestId('hod-momo-strip-empty').getAttribute('title')).toBeNull();
  });

  it('a day with no HOD Momo history states that absence -- never "No alerts raised" or "0 alerts"', () => {
    const day = { ...replay, date: '2026-07-15', minute: Date.parse('2026-07-15T07:20:00-04:00') / 1000, recorded: false };
    render(<HodMomoContextProvider value={contextValue(day, [])}><HodMomoDock /></HodMomoContextProvider>);
    const empty = screen.getByTestId('hod-momo-strip-empty');
    expect(empty.textContent).toBe('No HOD Momo alert history for 2026-07-15 -- Nova kept no HOD Momo record that day');
    expect(empty.textContent).not.toMatch(/No alerts raised/);
    expect(empty.getAttribute('title')).toMatch(/has its Scanner boards, not its alerts/);
    expect(screen.getByTestId('hod-momo-strip-since').textContent).toBe('no alert history');
    // The playhead still names the moment it stands at.
    expect(screen.getByTestId('hod-momo-strip-feed').textContent).toBe('replay 07:20');
  });

  it('live: Clear stays enabled and the feed says live', () => {
    render(<HodMomoContextProvider value={contextValue(null, [HISTORY[0]])}><HodMomoDock /></HodMomoContextProvider>);
    expect(screen.getByTestId('hod-momo-strip-feed').textContent).toBe('feed live');
    fireEvent.click(screen.getByTestId('hod-momo-strip-more'));
    expect((screen.getByTestId('hod-momo-dock-clear') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByTestId('hod-momo-dock-clear').hasAttribute('data-why')).toBe(false);
  });
});
