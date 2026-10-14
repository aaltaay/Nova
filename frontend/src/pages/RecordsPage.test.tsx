/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import type { AutoRecordStatus } from '../ibkr/types';
import type { CaptureSessions } from '../sim/useSimSessionController';
import { formatMissingSeconds, RecordsPage, todayEasternDate } from './RecordsPage';

const { captures, status, recording, replay, store, fetchMock } = vi.hoisted(() => ({
  captures: {
    state: { data: null as CaptureSessions | null, error: null as string | null },
    listeners: new Set<() => void>(),
  },
  status: { current: {} as IbkrClientStatus },
  recording: { symbols: [] as string[] },
  replay: { select: vi.fn() },
  store: { stop: vi.fn(), stopAll: vi.fn(), start: vi.fn() },
  fetchMock: vi.fn(),
}));

vi.mock('../sim/useSimSessionController', () => ({
  capturesResource: {
    getSnapshot: () => captures.state,
    subscribe: (l: () => void) => {
      captures.listeners.add(l);
      return () => captures.listeners.delete(l);
    },
    refresh: vi.fn(),
  },
}));
vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => status.current,
}));
vi.mock('../ibkr/ibkrStatusPoller', () => ({
  getIbkrStatusSnapshot: () => status.current,
  refreshIbkrStatusNow: vi.fn(),
  subscribeIbkrStatus: () => () => {},
}));
vi.mock('../capture/sessionRecordStore', () => ({
  useRecordingSymbols: () => recording.symbols,
  getRecordingSymbols: () => recording.symbols,
  getSessionRecordError: () => null,
  getSessionRecordVersion: () => 0,
  isTabRecording: () => false,
  subscribeSessionRecord: () => () => {},
  startTabRecord: store.start,
  stopTabRecord: store.stop,
  stopAllRecords: store.stopAll,
}));
vi.mock('../sim/captureReplayLoad', () => ({
  selectCaptureReplay: replay.select,
}));
vi.mock('../api/novaFetch', () => ({ novaFetch: fetchMock }));

function publish(next: typeof captures.state) {
  captures.state = next;
  captures.listeners.forEach((l) => l());
}

/** "-04:00" (EDT) or "-05:00" (EST): New York's offset on `day`, so a test of today passes all year. */
function etOffset(day: string): string {
  const noon = new Date(`${day}T12:00:00Z`);
  const hour = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', hourCycle: 'h23' })
    .format(noon));
  return `-0${12 - hour}:00`;
}
/** Epoch seconds of an ET clock time on `day`. */
const at = (day: string, hm: string) => Date.parse(`${day}T${hm}:00${etOffset(day)}`) / 1000;

const WINDOWS: AutoRecordStatus['windows'] = {
  open: 'setups',
  setups: {
    open: true, start: '07:00', end: '15:30', error: null,
    by_setup: [
      { setup: 'flat_top_5m', start: '07:00', end: '15:30', open: true },
      { setup: 'first_pullback', start: '07:00', end: '11:30', open: false },
      { setup: 'red_to_green', start: '09:30', end: '10:30', open: false },
    ],
  },
  leaders: { open: false, start: '07:00', end: '10:00' },
};

describe('RecordsPage', () => {
  let container: HTMLDivElement;
  let root: Root;
  const onOpenTrader = vi.fn();
  const today = todayEasternDate();

  beforeEach(() => {
    onOpenTrader.mockReset();
    replay.select.mockReset();
    store.stop.mockReset().mockResolvedValue(null);
    store.stopAll.mockReset().mockResolvedValue(null);
    store.start.mockReset().mockResolvedValue(null);
    fetchMock.mockReset();
    captures.state = { data: null, error: null };
    status.current = { connected: true, stale: false, mode: 'paper' } as IbkrClientStatus;
    recording.symbols = [];
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
    vi.useRealTimers();
  });

  function render() {
    act(() => {
      root.render(<RecordsPage onOpenTrader={onOpenTrader} />);
    });
  }

  const row = (testId: string) => container.querySelector(`[data-testid="${testId}"]`);
  const symbols = (date: string) =>
    [...row(`records-day-${date}`)!.querySelectorAll('tr[data-testid^="records-row-"]')]
      .map((tr) => tr.getAttribute('data-testid')!.split('-').pop());

  it('formats Eastern dates and missing seconds, hours included', () => {
    expect(todayEasternDate(new Date('2026-09-21T03:30:00Z'))).toBe('2026-09-20');
    expect(todayEasternDate(new Date('2026-09-21T12:30:00Z'))).toBe('2026-09-21');
    expect(formatMissingSeconds(undefined)).toBe('--');
    expect(formatMissingSeconds(0)).toBe('--');
    expect(formatMissingSeconds(42)).toBe('42s');
    expect(formatMissingSeconds(65)).toBe('1m 05s');
    expect(formatMissingSeconds(5 * 3600 + 12 * 60)).toBe('5h 12m');
  });

  it('opens the newest day, folds earlier ones, and says who ended each recording (V20, C22, C64)', () => {
    recording.symbols = ['GRML'];
    render();
    expect(container.textContent).toMatch(/Loading Session Records/);
    act(() => {
      publish({
        data: {
          root: 'F:\\Nova\\sim_capture',
          days: [{ date: today, ticker_count: 4 }, { date: '2020-01-02', ticker_count: 2 }],
          tickers_by_day: {
            [today]: [
              // A first segment still recording: the manifest has not counted it yet.
              { symbol: 'GRML', prints: null, l2: null, segments: 0, missing_sec: 0, usable: true, status: 'recording' },
              { symbol: 'IMCC', prints: 5, l2: 0, segments: 1, missing_sec: 0, empty: true, usable: false,
                unavailable_reason: 'No recorded prints or quotes' },
              { symbol: 'BYU', prints: 7, l2: 3, usable: true, status: 'stopped_partial_ok', last_reason: 'operator' },
              { symbol: 'AUT', prints: 7, l2: 3, usable: true, status: 'stopped_partial_ok', last_reason: 'auto' },
              { symbol: 'CUT', prints: 9, l2: 0, segments: 1, usable: true, status: 'interrupted' },
            ],
            '2020-01-02': [
              { symbol: 'OLD', prints: 1234, l2: 0, segments: 3, missing_sec: 65, usable: true, status: 'stopped_partial_ok' },
              { symbol: 'OLD2', prints: 9, l2: 0, segments: 1, usable: true, status: 'interrupted' },
            ],
          },
        },
        error: null,
      });
    });
    expect(container.textContent).toMatch(/Saved to F:\\Nova\\sim_capture/);
    expect(row('records-tab-sessions')!.textContent).toBe('Market data7');
    expect(row(`records-day-${today}`)!.closest('table')!.previousElementSibling).toBeTruthy();
    expect(container.querySelector('.records-dayhead h3')!.textContent).toMatch(/· today/);
    const grml = row(`records-row-${today}-GRML`)!;
    expect(grml.textContent).not.toMatch(/-1/);
    expect(grml.textContent).toMatch(/recording…/);
    expect(grml.textContent).toMatch(/Recording/);
    expect(row(`records-row-${today}-IMCC`)!.textContent).toMatch(/No recorded prints or quotes/);
    expect(row(`records-row-${today}-BYU`)!.textContent).toMatch(/Stopped by you/);
    expect(row(`records-row-${today}-AUT`)!.textContent).toMatch(/Stopped by auto-record/);
    expect(row(`records-row-${today}-CUT`)!.textContent).toMatch(/Cut by a Nova restart/);
    // The recording one is on top, and it is in Recording now.
    expect(symbols(today)[0]).toBe('GRML');
    expect(row('records-now-GRML')!.textContent).toMatch(/You started it/);
    // An earlier day is one folded line until it is opened.
    expect(row('records-day-2020-01-02')!.textContent).toMatch(/2 symbols · 1 cut by a restart/);
    expect(row('records-row-2020-01-02-OLD')).toBeNull();
    act(() => (row('records-day-toggle-2020-01-02') as HTMLButtonElement).click());
    const old = row('records-row-2020-01-02-OLD')!;
    expect(old.textContent).toMatch(/1,234/);
    expect(old.textContent).toMatch(/1m 05s/);
    expect(old.textContent).toMatch(/Stopped/);
    expect(old.textContent).not.toMatch(/stopped_partial_ok/);
    act(() => {
      (row('records-open-2020-01-02-OLD') as HTMLButtonElement).click();
    });
    expect(onOpenTrader).toHaveBeenCalledWith('OLD');
    // Replay is a Sim action; Paper shows none.
    expect(container.querySelector('[data-testid^="records-replay-"]')).toBeNull();
  });

  it('draws only the gaps the listing names: missing hatched, stopped on purpose dashed', () => {
    render();
    act(() => {
      publish({
        data: {
          days: [],
          tickers_by_day: {
            '2020-07-02': [{
              symbol: 'GAP', prints: 10, l2: 1, usable: true, status: 'stopped_partial_ok', last_reason: 'operator',
              missing_sec: 120,
              spans: [[at('2020-07-02', '09:00'), at('2020-07-02', '09:30')], [at('2020-07-02', '09:40'), at('2020-07-02', '10:00')],
                [at('2020-07-02', '10:02'), at('2020-07-02', '10:10')]],
              gaps: [[at('2020-07-02', '09:30'), at('2020-07-02', '09:40'), 'auto'],
                [at('2020-07-02', '10:00'), at('2020-07-02', '10:02'), 'restart']],
              bytes: { prints: 1_000_000, l2: 2_500_000, quotes: 0 },
            }],
          },
        },
        error: null,
      });
    });
    const gap = row('records-row-2020-07-02-GAP')!;
    expect(gap.querySelectorAll('[data-kind="span"]')).toHaveLength(3);
    expect(gap.querySelectorAll('[data-kind="missing"]')).toHaveLength(1);
    expect(gap.querySelectorAll('[data-kind="planned"]')).toHaveLength(1);
    expect(gap.textContent).toMatch(/2m 00s/);
    expect(gap.textContent).toMatch(/3\.5 MB/);
    expect(gap.textContent).toMatch(/58m 00s/);  // 30 + 20 + 8 minutes recorded
    expect(gap.querySelector('.records-gaps')!.getAttribute('title')).toBe(
      '09:30-09:40 ET stopped by auto-record\n10:00-10:02 ET missing: a Nova restart');
  });

  it('filters by chip and by symbol, and sorts by one header click with recording rows on top', () => {
    recording.symbols = ['GRML'];
    render();
    act(() => {
      publish({
        data: {
          days: [],
          tickers_by_day: {
            [today]: [
              { symbol: 'GRML', prints: null, l2: null, usable: true, status: 'recording' },
              { symbol: 'IMCC', prints: 5, l2: 0, usable: true, missing_sec: 30, status: 'stopped_partial_ok', last_reason: 'operator' },
              { symbol: 'APUS', prints: 80, l2: 0, usable: true, status: 'interrupted' },
            ],
          },
        },
        error: null,
      });
    });
    expect(row('records-chip-gaps')!.textContent).toBe('With gaps 1');
    act(() => (row('records-chip-gaps') as HTMLButtonElement).click());
    expect(symbols(today)).toEqual(['IMCC']);
    act(() => (row('records-chip-cut') as HTMLButtonElement).click());
    expect(symbols(today)).toEqual(['APUS']);
    act(() => (row('records-chip-you') as HTMLButtonElement).click());
    expect(symbols(today)).toEqual(['IMCC']);
    act(() => (row('records-chip-all') as HTMLButtonElement).click());
    const filter = row('records-filter') as HTMLInputElement;
    act(() => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      set.call(filter, 'ap');
      filter.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(symbols(today)).toEqual(['APUS']);
    act(() => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      set.call(filter, '');
      filter.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const prints = () => container.querySelector('th[data-sort-col="prints"]') as HTMLElement;
    act(() => prints().click());
    expect(symbols(today)).toEqual(['GRML', 'APUS', 'IMCC']);
    act(() => prints().click());
    expect(symbols(today)).toEqual(['GRML', 'IMCC', 'APUS']);
  });

  it('stops one recording after a full hold, and every one with Hold to stop all', async () => {
    vi.useFakeTimers();
    recording.symbols = ['COHQ', 'AXTQ'];
    status.current = {
      connected: true, stale: false, mode: 'paper',
      capture_sessions: [
        { symbol: 'COHQ', started_et: `${today}T13:58:00${etOffset(today)}`, segment_started_et: `${today}T14:36:00${etOffset(today)}`, segment: 2,
          counts: { prints: 29, quotes: 1, l2: 3457 } },
        { symbol: 'AXTQ', started_et: `${today}T14:44:00${etOffset(today)}`, segment_started_et: `${today}T14:44:00${etOffset(today)}`, segment: 1,
          counts: { prints: 3, quotes: 1, l2: 10 } },
      ],
      auto_record: {
        active: true, window: '', symbols: ['COHQ', 'AXTQ'], yielded: [], last_error: null,
        why: { COHQ: 'near', AXTQ: 'armed' }, setup: { COHQ: 'flat_top_5m', AXTQ: 'flat_top_5m' }, windows: WINDOWS,
        switch: { mode: 'on', source: 'default', day: null, until: null, error: null },
      },
    } as unknown as IbkrClientStatus;
    render();
    act(() => {
      publish({ data: { days: [], tickers_by_day: { [today]: [
        { symbol: 'COHQ', prints: 29, l2: 3457, usable: true, status: 'recording', last_reason: 'restart',
          spans: [[at(today, '13:58'), at(today, '14:20')], [at(today, '14:36'), at(today, '15:00')]] },
        { symbol: 'AXTQ', prints: 3, l2: 10, usable: true, status: 'recording' },
      ] } }, error: null });
    });
    const now = row('records-now')!;
    expect(now.textContent).toMatch(/2 of 3 recording slots in use/);
    expect(row('records-now-COHQ')!.textContent).toMatch(/Auto-record · 5-minute flat top · near its trigger/);
    expect(row('records-now-COHQ')!.textContent).toMatch(/since 13:58, resumed 14:36 after a Nova restart/);
    expect(row('records-now-free')!.textContent).toMatch(/free slot/);
    const stop = row('records-now-stop-COHQ') as HTMLElement;
    act(() => { stop.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 })); });
    act(() => { vi.advanceTimersByTime(600); });
    act(() => { stop.dispatchEvent(new PointerEvent('pointerup', { bubbles: true })); });
    act(() => { vi.advanceTimersByTime(1500); });
    expect(store.stop).not.toHaveBeenCalled();
    act(() => { stop.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 })); });
    await act(async () => { vi.advanceTimersByTime(1300); });
    expect(store.stop).toHaveBeenCalledWith('COHQ');
    const all = row('records-stop-all') as HTMLElement;
    act(() => { all.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 })); });
    await act(async () => { vi.advanceTimersByTime(1300); });
    expect(store.stopAll).toHaveBeenCalledTimes(1);
  });

  it('turns auto-record off from its switch, and says what it would stop and why it is locked', async () => {
    const auto = (over: Partial<AutoRecordStatus>): IbkrClientStatus => ({
      connected: true, stale: false, mode: 'paper',
      auto_record: {
        active: true, window: '', symbols: ['COHQ'], yielded: [], last_error: null, windows: WINDOWS,
        switch: { mode: 'on', source: 'default', day: null, until: null, error: null }, ...over,
      },
    }) as unknown as IbkrClientStatus;
    status.current = auto({});
    render();
    act(() => publish({ data: { days: [], tickers_by_day: {} }, error: null }));
    const card = row('records-auto-record')!;
    expect(card.textContent).toMatch(/Turning it off stops COHQ now/);
    expect(row('records-auto-windows')!.textContent).toMatch(/5-minute flat top/);
    expect(row('records-auto-on')!.getAttribute('aria-pressed')).toBe('true');
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) } as Response);
    await act(async () => { (row('records-auto-off_today') as HTMLButtonElement).click(); });
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/auto-record$/), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ mode: 'off_today' }),
    }));
    fetchMock.mockResolvedValueOnce({
      ok: false, status: 503, json: async () => ({ detail: 'Nova could not save the switch (OSError: full)' }),
    } as Response);
    await act(async () => { (row('records-auto-off') as HTMLButtonElement).click(); });
    expect(card.textContent).toMatch(/The switch did not change: Nova could not save the switch/);

    status.current = auto({ symbols: [], switch: { mode: 'off', source: 'env', day: null, until: null, error: null } });
    render();
    expect(row('records-auto-on')!.hasAttribute('disabled')).toBe(true);
    expect(row('records-auto-on')!.getAttribute('data-why')).toMatch(/NOVA_AUTO_RECORD=0/);
    status.current = auto({ switch: undefined });
    render();
    expect(row('records-auto-on')!.getAttribute('data-why')).toMatch(/did not say how auto-record is set/);
    // Off for today: nothing records, and the card offers to turn it back on.
    status.current = auto({ symbols: [], switch: { mode: 'off_today', source: 'operator', day: today, until: null, error: null } });
    render();
    expect(row('records-now')!.textContent).toMatch(/Auto-record is off for today/);
    expect(row('records-auto-on-now')).toBeTruthy();
  });

  it('never offers the removed synthetic SIM1 session as a recording (C21)', () => {
    status.current = { connected: true, stale: false, mode: 'sim' } as IbkrClientStatus;
    render();
    act(() => {
      publish({
        data: {
          days: [{ date: '2026-09-19', ticker_count: 2 }],
          tickers_by_day: {
            '2026-09-19': [
              { symbol: 'SIM1', prints: 172020, l2: 5, usable: true, source: 'sim', status: 'generated_full_day' },
              { symbol: 'GRML', prints: 10, l2: 1, usable: true, source: 'ibkr', status: 'stopped_partial_ok' },
            ],
          },
        },
        error: null,
      });
    });
    expect(row('records-row-2026-09-19-SIM1')!.textContent).toMatch(/Not a Session Record/);
    expect(row('records-replay-2026-09-19-SIM1')).toBeNull();
    expect(row('records-replay-2026-09-19-GRML')).toBeTruthy();
  });

  it('replays a Session Record in Sim and opens it in Trader; a refused load is stated (V20)', async () => {
    status.current = { connected: true, stale: false, mode: 'sim' } as IbkrClientStatus;
    render();
    act(() => {
      publish({
        data: { days: [], tickers_by_day: { '2026-09-19': [{ symbol: 'GRML', prints: 10, l2: 1, usable: true }] } },
        error: null,
      });
    });
    replay.select.mockResolvedValueOnce({ clock: { sim: true, replay_ok: true }, complete: true });
    await act(async () => {
      (row('records-replay-2026-09-19-GRML') as HTMLButtonElement).click();
    });
    expect(replay.select).toHaveBeenCalledWith(expect.any(Function), '2026-09-19', 'GRML');
    expect(onOpenTrader).toHaveBeenCalledWith('GRML');
    onOpenTrader.mockReset();
    replay.select.mockResolvedValueOnce({
      clock: { sim: true, replay_ok: false, replay_error: 'Capture contains no usable prints or quotes' }, complete: true,
    });
    await act(async () => {
      (row('records-replay-2026-09-19-GRML') as HTMLButtonElement).click();
    });
    expect(onOpenTrader).not.toHaveBeenCalled();
    expect(row('records-page-replay-error')!.textContent).toMatch(/no usable prints/);
  });

  it('says so when there are no Session Records, when the listing is unavailable, and survives a malformed one (C13)', () => {
    render();
    act(() => {
      publish({ data: { days: [], tickers_by_day: {} }, error: null });
    });
    expect(row('records-page-empty')).toBeTruthy();
    act(() => {
      publish({ data: { days: [] } as unknown as CaptureSessions, error: null });
    });
    expect(row('records-page-empty')).toBeTruthy();
    act(() => {
      publish({ data: null, error: 'HTTP 503' });
    });
    expect(container.querySelector('[role="alert"]')!.textContent).toMatch(/unavailable: HTTP 503/);
  });
});
