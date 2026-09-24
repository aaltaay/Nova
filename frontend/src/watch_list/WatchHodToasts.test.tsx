/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { publishHodMomoLiveAlert } from '../hod_momo/hodMomoLiveAlerts';
import type { AlertObject } from '../hod_momo/types';
import { WATCH_TOAST_TTL_MS } from './watchListConstants';
import { WatchHodToasts } from './WatchHodToasts';
import { addToWatchList, getWatchList, resetWatchListForTests } from './watchListStore';
import { resetWatchToastsForTests } from './watchToasts';

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

describe('WatchHodToasts', () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
  });

  it('toasts a watched symbol that hits HOD Momo, with its facts, and nothing for the rest', () => {
    addToWatchList('GRML');
    render(<WatchHodToasts onOpenSymbol={vi.fn()} />);
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
    render(<WatchHodToasts />);
    act(() => publishHodMomoLiveAlert(hodAlert('GRML', 12, 'Running Up Alert')));
    expect(screen.getByTestId('watch-toast').textContent).toContain('GRML is running up');
    act(() => publishHodMomoLiveAlert(hodAlert('GRML', 1, 'New High of Day')));
    expect(screen.getAllByTestId('watch-toast')).toHaveLength(1);
    expect(screen.getByTestId('watch-toast').textContent).toContain('GRML hit HOD Momo');
    expect(screen.getByTestId('watch-toast-body').textContent).toBe('New High of Day · Running Up Alert · 2 alerts');
  });

  it('folds a burst into one toast with a count', () => {
    addToWatchList('GRML');
    render(<WatchHodToasts />);
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
    render(<WatchHodToasts onOpenSymbol={onOpen} />);
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
    render(<WatchHodToasts />);
    act(() => publishHodMomoLiveAlert(hodAlert('GRML')));
    fireEvent.mouseEnter(screen.getByTestId('watch-toast'));
    act(() => { vi.advanceTimersByTime(WATCH_TOAST_TTL_MS + 1_000); });
    expect(screen.getByTestId('watch-toast')).toBeTruthy();
    fireEvent.mouseLeave(screen.getByTestId('watch-toast'));
    act(() => { vi.advanceTimersByTime(WATCH_TOAST_TTL_MS + 1); });
    expect(screen.queryByTestId('watch-toast')).toBeNull();
  });
});
