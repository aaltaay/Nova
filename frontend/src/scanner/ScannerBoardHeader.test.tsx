/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  publishGlobalBarCore,
  resetScannerBarStoreForTests,
  setGlobalBarHistoryDates,
} from '../components/scannerBarStore';
import { SCANNER_BOARD_FILTERS_STORAGE_KEY } from '../constantGroups/scanner_board';
import { ScannerBoardFooter } from './ScannerBoardFooter';
import { fmtScannedAgo, ScannerBoardHeader } from './ScannerBoardHeader';
import { useBoardFilters } from './useBoardFilters';

const promptMock = vi.fn<(input: unknown) => Promise<string | null>>();
vi.mock('../ux', () => ({
  promptApp: (input: unknown) => promptMock(input),
}));

function Harness({ scannedAgoSec = 6 }: { scannedAgoSec?: number | null }) {
  const filters = useBoardFilters();
  return (
    <>
      <ScannerBoardHeader title="Gappers" filters={filters} scannedAgoSec={scannedAgoSec} />
      <div data-testid="active">{[...filters.active].join(',')}</div>
    </>
  );
}

afterEach(() => {
  cleanup();
  localStorage.removeItem(SCANNER_BOARD_FILTERS_STORAGE_KEY);
  promptMock.mockReset();
  resetScannerBarStoreForTests();
});

describe('ScannerBoardHeader', () => {
  it('shows the title, the chips, the saved menu and the session line', () => {
    render(<Harness />);
    expect(screen.getByTestId('selected-scanner-title').textContent).toBe('Gappers');
    expect(screen.getByTestId('scanner-chip-gap').textContent).toBe('Gap ≥ 10%');
    expect(screen.getByTestId('scanner-chip-halted').getAttribute('aria-disabled')).toBe('true');
    expect(screen.getByTestId('scanner-board-saved').textContent).toContain('Saved:');
    expect(screen.getByTestId('scanner-board-phase').textContent).toMatch(/Opens in|Closes in|After hours/);
    expect(screen.getByTestId('scanner-board-scanned').textContent).toBe('Scanned 6s ago');
  });

  it('states when the list never scanned', () => {
    render(<Harness scannedAgoSec={null} />);
    expect(screen.getByTestId('scanner-board-scanned').textContent).toBe('Not scanned yet');
  });

  it('says a scan age in minutes or hours, never raw seconds (QA V27 / C67)', () => {
    expect(fmtScannedAgo(6)).toBe('6s');
    expect(fmtScannedAgo(89)).toBe('89s');
    expect(fmtScannedAgo(1455)).toBe('24m');
    expect(fmtScannedAgo(3130)).toBe('52m');
    expect(fmtScannedAgo(3 * 3600 + 5 * 60)).toBe('3h 05m');
    render(<Harness scannedAgoSec={3130} />);
    expect(screen.getByTestId('scanner-board-scanned').textContent).toBe('Scanned 52m ago');
  });

  it('names a failed scanner route on the board (QA C31)', () => {
    render(<ScannerBoardHeader title="Gainers" filters={null} scannedAgoSec={null} feedFailure="Scanner feed failed: /api/movers answered HTTP 500" />);
    expect(screen.getByTestId('scanner-board-feed-failed').textContent).toContain('/api/movers answered HTTP 500');
  });

  it('toggles chips as real filters (persisted) and ignores the unavailable one', () => {
    render(<Harness />);
    fireEvent.click(screen.getByTestId('scanner-chip-gap'));
    fireEvent.click(screen.getByTestId('scanner-chip-news'));
    expect(screen.getByTestId('active').textContent).toBe('gap,news');
    expect(screen.getByTestId('scanner-chip-gap').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('scanner-chip-halted'));
    expect(screen.getByTestId('active').textContent).toBe('gap,news');
    expect(JSON.parse(localStorage.getItem(SCANNER_BOARD_FILTERS_STORAGE_KEY) ?? '{}').value.active).toEqual(['gap', 'news']);
  });

  it('the unavailable chip carries its reason for the locked-control tip; working chips keep their title', () => {
    render(<Harness />);
    const halted = screen.getByTestId('scanner-chip-halted');
    expect(halted.getAttribute('data-why')).toMatch(/Halt state is not carried on scanner rows yet/);
    expect(halted.hasAttribute('title')).toBe(false);
    const gap = screen.getByTestId('scanner-chip-gap');
    expect(gap.hasAttribute('data-why')).toBe(false);
    expect(gap.getAttribute('title')).toMatch(/at least 10%/);
  });

  it('the history picker on the sample desk says why it is locked', () => {
    render(<Harness />);
    act(() => {
      publishGlobalBarCore({
        mode: 'premarket',
        health: { status: 'connected', latency_ms: 1 },
        activeFeed: 'ibkr',
        feedFellBack: false,
        onHistoryChange: () => {},
        onLookup: () => {},
        sampleDataActive: true,
      });
    });
    const select = screen.getByTestId('scanner-board-history') as HTMLSelectElement;
    expect(select.disabled).toBe(true);
    expect(select.getAttribute('data-why')).toMatch(/exit sample data to browse past boards/);
    // '' keeps the session line's own title from showing over the reason.
    expect(select.getAttribute('title')).toBe('');
  });

  it('saves the current chips under a name and applies a saved set', async () => {
    promptMock.mockResolvedValue('Low-float runners');
    render(<Harness />);
    fireEvent.click(screen.getByTestId('scanner-chip-gap'));
    fireEvent.click(screen.getByTestId('scanner-board-saved'));
    expect(screen.getByTestId('scanner-board-saved-menu').textContent).toContain('No saved sets yet');
    await act(async () => {
      fireEvent.click(screen.getByTestId('scanner-board-saved-save'));
    });
    expect(promptMock).toHaveBeenCalled();
    expect(screen.getByTestId('scanner-board-saved').textContent).toContain('Low-float runners');

    fireEvent.click(screen.getByTestId('scanner-chip-gap'));
    expect(screen.getByTestId('active').textContent).toBe('');
    fireEvent.click(screen.getByTestId('scanner-board-saved'));
    fireEvent.click(screen.getByTestId('scanner-board-saved-item'));
    expect(screen.getByTestId('active').textContent).toBe('gap');
    expect(screen.queryByTestId('scanner-board-saved-menu')).toBeNull();
  });

  it('leads the session line with the Today (Live) history picker once the bar has published', () => {
    render(<Harness />);
    expect(screen.queryByTestId('scanner-board-history')).toBeNull();
    const onHistoryChange = vi.fn();
    act(() => {
      publishGlobalBarCore({
        mode: 'premarket',
        health: { status: 'connected', latency_ms: 1 },
        activeFeed: 'ibkr',
        feedFellBack: false,
        onHistoryChange,
        onLookup: () => {},
      });
      setGlobalBarHistoryDates(['2026-09-18']);
    });
    const select = screen.getByTestId('scanner-board-history') as HTMLSelectElement;
    expect(select.options[0].textContent).toBe('Today (Live)');
    expect(select.options[1].textContent).toMatch(/Sep 18/);
    expect(select.disabled).toBe(false);
    expect(screen.getByTestId('scanner-board-session').firstElementChild).toBe(select);
    fireEvent.change(select, { target: { value: '2026-09-18' } });
    expect(onHistoryChange).toHaveBeenCalledTimes(1);
  });

  it('renders without chips for a non-scanner list', () => {
    render(<ScannerBoardHeader title="Watchlist" filters={null} scannedAgoSec={undefined} />);
    expect(screen.queryByTestId('scanner-chip-gap')).toBeNull();
    expect(screen.getByTestId('scanner-board-session')).toBeTruthy();
    expect(screen.queryByTestId('scanner-board-scanned')).toBeNull();
  });
});

describe('ScannerBoardFooter', () => {
  it('states the match count, what the chips hid (with Show all) and what the exchange filter hid', () => {
    const onShowAll = vi.fn();
    render(<ScannerBoardFooter shown={12} total={41} hiddenByChips={27} hiddenByExchange={2} noun="gappers" onShowAll={onShowAll} />);
    expect(screen.getByTestId('scanner-board-match').textContent).toBe('12 of 41 gappers match');
    expect(screen.getByTestId('scanner-board-hidden-chips').textContent).toContain('27 more hidden by your filters');
    expect(screen.getByTestId('scanner-board-hidden-exchange').textContent).toContain('2 hidden by the exchange filter');
    fireEvent.click(screen.getByTestId('scanner-board-show-all'));
    expect(onShowAll).toHaveBeenCalled();
  });

  it('is quiet about hiding when nothing is hidden', () => {
    render(<ScannerBoardFooter shown={5} total={5} hiddenByChips={0} hiddenByExchange={0} noun="gainers" onShowAll={() => {}} />);
    expect(screen.queryByTestId('scanner-board-hidden-chips')).toBeNull();
    expect(screen.queryByTestId('scanner-board-hidden-exchange')).toBeNull();
    expect(screen.getByText('recording')).toBeTruthy();
  });

  it('useBoardFilters filterRows is stable per active set (memo input)', () => {
    const { result, rerender } = renderHook(() => useBoardFilters());
    const first = result.current.filterRows;
    rerender();
    expect(result.current.filterRows).toBe(first);
  });
});
