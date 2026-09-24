/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import type { CaptureSessions } from '../sim/useSimSessionController';
import { formatMissingSeconds, RecordsPage, todayEasternDate } from './RecordsPage';

const { captures, status, recording, replay } = vi.hoisted(() => ({
  captures: {
    state: { data: null as CaptureSessions | null, error: null as string | null },
    listeners: new Set<() => void>(),
  },
  status: { current: {} as IbkrClientStatus },
  recording: { symbols: [] as string[] },
  replay: { select: vi.fn() },
}));

vi.mock('../sim/useSimSessionController', () => ({
  capturesResource: {
    getSnapshot: () => captures.state,
    subscribe: (l: () => void) => {
      captures.listeners.add(l);
      return () => captures.listeners.delete(l);
    },
  },
}));
vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => status.current,
}));
vi.mock('../capture/sessionRecordStore', () => ({
  useRecordingSymbols: () => recording.symbols,
}));
vi.mock('../sim/captureReplayLoad', () => ({
  selectCaptureReplay: replay.select,
}));

function publish(next: typeof captures.state) {
  captures.state = next;
  captures.listeners.forEach((l) => l());
}

describe('RecordsPage', () => {
  let container: HTMLDivElement;
  let root: Root;
  const onOpenTrader = vi.fn();
  const today = todayEasternDate();

  beforeEach(() => {
    onOpenTrader.mockReset();
    replay.select.mockReset();
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
  });

  function render() {
    act(() => {
      root.render(<RecordsPage onOpenTrader={onOpenTrader} />);
    });
  }

  const row = (testId: string) => container.querySelector(`[data-testid="${testId}"]`);

  it('formats Eastern dates and missing seconds, hours included', () => {
    expect(todayEasternDate(new Date('2026-09-21T03:30:00Z'))).toBe('2026-09-20');
    expect(todayEasternDate(new Date('2026-09-21T12:30:00Z'))).toBe('2026-09-21');
    expect(formatMissingSeconds(undefined)).toBe('--');
    expect(formatMissingSeconds(0)).toBe('--');
    expect(formatMissingSeconds(42)).toBe('42s');
    expect(formatMissingSeconds(65)).toBe('1m 05s');
    expect(formatMissingSeconds(5 * 3600 + 12 * 60)).toBe('5h 12m');
  });

  it('lists every day newest first, today marked, with words for statuses and unknown counts (V20, C22, C64)', () => {
    recording.symbols = ['GRML'];
    render();
    expect(container.textContent).toMatch(/Loading Session Records/);
    act(() => {
      publish({
        data: {
          days: [{ date: today, ticker_count: 2 }, { date: '2020-01-02', ticker_count: 2 }],
          tickers_by_day: {
            [today]: [
              // A first segment still recording: the manifest has not counted it yet.
              { symbol: 'GRML', prints: null, l2: null, segments: 0, missing_sec: 0, usable: true, status: 'recording' },
              { symbol: 'IMCC', prints: 5, l2: 0, segments: 1, missing_sec: 0, empty: true, usable: false,
                unavailable_reason: 'No recorded prints or quotes' },
            ],
            '2020-01-02': [
              { symbol: 'OLD', prints: 1234, l2: 0, segments: 3, missing_sec: 65, usable: true, status: 'stopped_partial_ok' },
              { symbol: 'CUT', prints: 9, l2: 0, segments: 1, usable: true, status: 'interrupted' },
            ],
          },
        },
        error: null,
      });
    });
    const days = [...container.querySelectorAll('[data-testid^="records-day-"]')].map((el) => el.getAttribute('data-testid'));
    expect(days).toEqual([`records-day-${today}`, 'records-day-2020-01-02']);
    expect(row(`records-day-${today}`)!.textContent).toMatch(/· today/);
    expect(row('records-page-recording')!.textContent).toMatch(/GRML/);
    const grml = row(`records-row-${today}-GRML`)!;
    expect(grml.textContent).not.toMatch(/-1/);
    expect(grml.textContent).toMatch(/recording…/);
    expect(grml.textContent).toMatch(/Recording/);
    expect(row(`records-row-${today}-IMCC`)!.textContent).toMatch(/No recorded prints or quotes/);
    const old = row('records-row-2020-01-02-OLD')!;
    expect(old.textContent).toMatch(/1,234/);
    expect(old.textContent).toMatch(/1m 05s/);
    expect(old.textContent).toMatch(/Stopped/);
    expect(old.textContent).not.toMatch(/stopped_partial_ok/);
    expect(row('records-row-2020-01-02-CUT')!.textContent).toMatch(/Cut by a Nova restart/);
    act(() => {
      (row('records-open-2020-01-02-OLD') as HTMLButtonElement).click();
    });
    expect(onOpenTrader).toHaveBeenCalledWith('OLD');
    // Replay is a Sim action; Paper shows none.
    expect(container.querySelector('[data-testid^="records-replay-"]')).toBeNull();
  });

  it('sorts every day by one header click, days kept newest first and uncounted prints last', () => {
    render();
    act(() => {
      publish({
        data: {
          days: [],
          tickers_by_day: {
            [today]: [
              { symbol: 'GRML', prints: null, l2: null, usable: true },
              { symbol: 'IMCC', prints: 5, l2: 0, usable: true },
              { symbol: 'APUS', prints: 80, l2: 0, usable: true },
            ],
            '2020-01-02': [
              { symbol: 'CUT', prints: 9, l2: 0, usable: true },
              { symbol: 'OLD', prints: 1234, l2: 0, usable: true },
            ],
          },
        },
        error: null,
      });
    });
    const symbols = (date: string) =>
      [...row(`records-day-${date}`)!.querySelectorAll('tbody tr')].map((tr) => tr.firstElementChild!.textContent);
    const prints = () => container.querySelectorAll('th[data-sort-col="prints"]');
    expect(symbols(today)).toEqual(['GRML', 'IMCC', 'APUS']);

    act(() => (prints()[1] as HTMLElement).click());
    expect(symbols(today)).toEqual(['APUS', 'IMCC', 'GRML']);
    expect(symbols('2020-01-02')).toEqual(['OLD', 'CUT']);
    expect([...prints()].map((th) => th.getAttribute('aria-sort'))).toEqual(['descending', 'descending']);
    const days = [...container.querySelectorAll('[data-testid^="records-day-"]')].map((el) => el.getAttribute('data-testid'));
    expect(days).toEqual([`records-day-${today}`, 'records-day-2020-01-02']);

    act(() => (prints()[0] as HTMLElement).click());
    // Lowest first; the recording Nova has not counted stays last.
    expect(symbols(today)).toEqual(['IMCC', 'APUS', 'GRML']);
    expect(symbols('2020-01-02')).toEqual(['CUT', 'OLD']);
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
