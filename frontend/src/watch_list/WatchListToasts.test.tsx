/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { publishHodMomoLiveAlert } from '../hod_momo/hodMomoLiveAlerts';
import type { AlertObject } from '../hod_momo/types';
import type { SetupRow, SetupsBoard } from '../setups';
import { FIXTURE_LEG_B, setupBoard, setupRow } from './setupFixtures';
import { WATCH_SETUP_UNLISTED, WATCH_TOAST_TTL_MS } from './watchListConstants';
import { WatchListToasts } from './WatchListToasts';
import { addToWatchList, getWatchList, resetWatchListForTests } from './watchListStore';
import { resetWatchToastsForTests } from './watchToasts';

// The desk's one /ws/setups board, as the provider would hand it over.
const setups = vi.hoisted(() => ({ value: null as { board: SetupsBoard | null; connected: boolean } | null }));
vi.mock('../setups', async importOriginal => ({
  ...(await importOriginal<typeof import('../setups')>()),
  useSetupsBoard: () => setups.value,
}));

function hodAlert(ticker: string, strategy_id = 1, strategy_name = 'New High of Day'): AlertObject {
  return {
    id: `${ticker}-${strategy_id}-${strategy_name}`,
    timestamp: '2026-09-23T14:14:05Z',
    created_ts: Date.UTC(2026, 8, 23, 14, 14, 5) / 1000,
    ticker,
    strategy_id,
    strategy_name,
    price: 4.52,
    change_pct: 38.2,
    rvol: 5.2,
    float_shares: 3_000_000,
    gap_pct: 20,
    volume: 2_100_000,
    momentum_pct: null,
    rvol_source: 'alpaca',
    consolidation_count: 1,
    consolidated_ids: [],
  };
}

/** Hands the toasts a new frame, as the socket would. */
function frame(rows: SetupRow[], patch: Partial<SetupsBoard> = {}, connected = true): SetupsBoard {
  const board = setupBoard(rows, patch);
  setups.value = { board, connected };
  return board;
}

const titles = () => screen.queryAllByTestId('watch-toast-title').map(t => t.textContent);

describe('WatchListToasts', () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
    setups.value = null;
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
    setups.value = null;
  });

  it('toasts a watched symbol that hits HOD Momo, with its facts, and nothing for the rest', () => {
    addToWatchList('GRML');
    render(<WatchListToasts onOpenSymbol={vi.fn()} />);
    act(() => publishHodMomoLiveAlert(hodAlert('ONCO')));
    expect(screen.queryByTestId('watch-toast')).toBeNull();
    act(() => publishHodMomoLiveAlert(hodAlert('GRML')));
    const toast = screen.getByTestId('watch-toast');
    expect(toast.textContent).toContain('GRML hit HOD Momo');
    expect(toast.textContent).toContain('10:14:05');
    expect(screen.getByTestId('watch-toast-body').textContent).toBe('New High of Day');
    expect(screen.getByTestId('watch-toast-facts').textContent).toBe('$4.52 · +38.20% · Vol 2.1M · RVOL 5.2x');
  });

  it('toasts Running Up as "is running up" until a HOD Momo strategy joins it', () => {
    addToWatchList('GRML');
    render(<WatchListToasts />);
    act(() => publishHodMomoLiveAlert(hodAlert('GRML', 12, 'Running Up Alert')));
    expect(screen.getByTestId('watch-toast').textContent).toContain('GRML is running up');
    act(() => publishHodMomoLiveAlert(hodAlert('GRML', 1, 'New High of Day')));
    expect(screen.getAllByTestId('watch-toast')).toHaveLength(1);
    expect(screen.getByTestId('watch-toast').textContent).toContain('GRML hit HOD Momo');
    expect(screen.getByTestId('watch-toast-body').textContent).toBe('New High of Day · Running Up Alert · 2 alerts');
  });

  it('folds a burst into one toast with a count', () => {
    addToWatchList('GRML');
    render(<WatchListToasts />);
    act(() => {
      publishHodMomoLiveAlert(hodAlert('GRML', 1, 'New High of Day'));
      publishHodMomoLiveAlert(hodAlert('GRML', 3, 'Squeeze'));
    });
    expect(screen.getAllByTestId('watch-toast')).toHaveLength(1);
    expect(screen.getByTestId('watch-toast-body').textContent).toBe('Squeeze · New High of Day · 2 alerts');
  });

  it('Open goes to the symbol, Stop watching takes it off the list, and × dismisses', () => {
    addToWatchList('GRML');
    addToWatchList('ONCO');
    const onOpen = vi.fn();
    render(<WatchListToasts onOpenSymbol={onOpen} />);
    act(() => publishHodMomoLiveAlert(hodAlert('GRML')));
    fireEvent.click(screen.getByTestId('watch-toast-open'));
    expect(onOpen).toHaveBeenCalledWith('GRML');
    expect(screen.queryByTestId('watch-toast')).toBeNull();

    act(() => publishHodMomoLiveAlert(hodAlert('ONCO')));
    fireEvent.click(screen.getByTestId('watch-toast-unwatch'));
    expect(getWatchList()).toEqual(['GRML']);
    expect(screen.queryByTestId('watch-toast')).toBeNull();

    act(() => publishHodMomoLiveAlert(hodAlert('GRML', 2, 'Squeeze')));
    fireEvent.click(screen.getByTestId('watch-toast-dismiss'));
    expect(screen.queryByTestId('watch-toast')).toBeNull();
  });

  it('leaves on its own after the TTL, but not while hovered', () => {
    vi.useFakeTimers();
    addToWatchList('GRML');
    render(<WatchListToasts />);
    act(() => publishHodMomoLiveAlert(hodAlert('GRML')));
    fireEvent.mouseEnter(screen.getByTestId('watch-toast'));
    act(() => { vi.advanceTimersByTime(WATCH_TOAST_TTL_MS + 1_000); });
    expect(screen.getByTestId('watch-toast')).toBeTruthy();
    fireEvent.mouseLeave(screen.getByTestId('watch-toast'));
    act(() => { vi.advanceTimersByTime(WATCH_TOAST_TTL_MS + 1); });
    expect(screen.queryByTestId('watch-toast')).toBeNull();
  });
});

describe('WatchListToasts on the setup scanner', () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
    setups.value = null;
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
    setups.value = null;
  });

  it("toasts a watched symbol's setup as it climbs -- never what the first frame already showed", () => {
    addToWatchList('GRML');
    frame([setupRow('GRML', 'armed'), setupRow('ONCO', 'leg')]);
    const { rerender } = render(<WatchListToasts />);
    expect(screen.queryByTestId('watch-toast')).toBeNull();

    frame([
      setupRow('GRML', 'near', { reason: '0.02 under the 4.37 trigger -- read the tape', tape: { verdict: 'go', reasons: [] } }),
      setupRow('ONCO', 'armed'),
    ]);
    rerender(<WatchListToasts />);
    expect(titles()).toEqual(['GRML: first pullback near the trigger']);
    const line = screen.getByTestId('watch-toast-setup');
    expect(line.textContent).toContain('First pullback');
    expect(line.textContent).toContain('Near');
    expect(line.textContent).toContain('0.02 under the 4.37 trigger — read the tape · Tape: go');
    expect(line.getAttribute('data-tip')).toContain('Price is a few cents under the trigger');
    expect(screen.getByTestId('watch-toast-facts').textContent).toBe('Last $4.35');
  });

  it('names what the trigger is, and folds a HOD alert and the setup into one toast', () => {
    addToWatchList('PFSA');
    const r2g = (state: 'leg' | 'near') => setupRow('PFSA', state, { setup_type: 'red_to_green', kind: 'red_to_green' });
    frame([]);
    const { rerender } = render(<WatchListToasts />);
    act(() => publishHodMomoLiveAlert(hodAlert('PFSA', 12, 'Running Up Alert')));
    expect(titles()).toEqual(['PFSA is running up']);

    frame([r2g('leg')]);
    rerender(<WatchListToasts />);
    expect(titles()).toEqual(['PFSA: red to green forming']);
    frame([r2g('near')]);
    rerender(<WatchListToasts />);
    expect(titles()).toEqual(['PFSA: red to green near the open']);
    // The running-up line and its facts stay on the one toast.
    expect(screen.getByTestId('watch-toast-body').textContent).toBe('Running Up Alert');
    expect(screen.getByTestId('watch-toast-facts').textContent).toContain('$4.52');
    expect(screen.getAllByTestId('watch-toast-setup')).toHaveLength(1);
  });

  it('never toasts from the Sim board, and reads the first frame after a reconnect silently', () => {
    addToWatchList('GRML');
    frame([]);
    const { rerender } = render(<WatchListToasts />);
    frame([setupRow('GRML', 'armed')], { source: 'sim' });
    rerender(<WatchListToasts />);
    frame([setupRow('GRML', 'armed')]);          // back on the live board: a baseline
    rerender(<WatchListToasts />);
    expect(screen.queryByTestId('watch-toast')).toBeNull();

    const board = frame([setupRow('GRML', 'armed')]);
    rerender(<WatchListToasts />);
    setups.value = { board, connected: false };    // the socket drops ...
    rerender(<WatchListToasts />);
    setups.value = { board, connected: true };     // ... and comes back on the old frame
    rerender(<WatchListToasts />);
    frame([setupRow('GRML', 'triggered')]);      // what happened while away is not news
    rerender(<WatchListToasts />);
    expect(screen.queryByTestId('watch-toast')).toBeNull();

    frame([setupRow('GRML', 'armed', {}, FIXTURE_LEG_B)]);
    rerender(<WatchListToasts />);
    expect(titles()).toEqual(['GRML: first pullback armed']);
  });

  it('keeps each setup line on the board while the toast is up, without restarting its timer', () => {
    vi.useFakeTimers();
    addToWatchList('GRML');
    frame([]);
    const { rerender } = render(<WatchListToasts />);
    frame([setupRow('GRML', 'armed')]);
    rerender(<WatchListToasts />);
    act(() => { vi.advanceTimersByTime(WATCH_TOAST_TTL_MS - 1_000); });

    frame([setupRow('GRML', 'failed', { reason: 'gave back half the leg' })]);
    rerender(<WatchListToasts />);
    expect(titles()).toEqual(['GRML: first pullback armed']);
    expect(screen.getByTestId('watch-toast-setup').textContent).toContain('Failed');
    expect(screen.getByTestId('watch-toast-setup').textContent).toContain('gave back half the leg');

    frame([]);
    rerender(<WatchListToasts />);
    expect(screen.getByTestId('watch-toast-setup').textContent).toContain(WATCH_SETUP_UNLISTED);
    act(() => { vi.advanceTimersByTime(1_001); });
    expect(screen.queryByTestId('watch-toast')).toBeNull();
  });
});
