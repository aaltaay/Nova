/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetPinnedRowsForTests, getPinnedRows } from '../scanner/pinnedRowsStore';
import { fakeHotList } from '../hot_list/hotListFake';
import { addToWatchList, getWatchList, resetWatchListForTests } from '../watch_list/watchListStore';

// The watch list is today's hot list (ADR 044): an in-memory one here.
vi.mock('../hot_list', async () => (await import('../hot_list/hotListFake')).hotListFakeModule());
import { ScannerRowActions } from './ScannerRowActions';
import { ScannerRowMarks } from './ScannerRowMarks';

const facts = { recording: false };
vi.mock('./useScannerRowFacts', () => ({
  useScannerRowFacts: () => facts,
}));

const record = { start: vi.fn(async () => null as string | null), stop: vi.fn(async () => null as string | null) };
vi.mock('../capture/sessionRecordStore', () => ({
  startTabRecord: (s: string) => record.start(s),
  stopTabRecord: (s: string) => record.stop(s),
}));

describe('ScannerRowActions', () => {
  beforeEach(() => {
    facts.recording = false;
    record.start.mockClear();
    record.stop.mockClear();
    _resetPinnedRowsForTests();
  });

  afterEach(() => {
    cleanup();
  });

  it('opens Trader, starts a recording and pins -- and never reaches the row', () => {
    const onOpenTrading = vi.fn();
    const rowClick = vi.fn();
    render(
      <div onClick={rowClick}>
        <ScannerRowActions symbol="GRML" onOpenTrading={onOpenTrading} />
      </div>,
    );
    fireEvent.click(screen.getByTestId('scanner-row-trader'));
    expect(onOpenTrading).toHaveBeenCalledWith('GRML');
    fireEvent.click(screen.getByTestId('scanner-row-record'));
    expect(record.start).toHaveBeenCalledWith('GRML');
    // The strategies only watch (ADR 072): no row button lets a bot trade the symbol.
    expect(screen.queryByTestId('scanner-row-allowlist')).toBeNull();
    expect(screen.getByTestId('scanner-row-pin').textContent).toBe('Pin');
    fireEvent.click(screen.getByTestId('scanner-row-pin'));
    expect(getPinnedRows().has('GRML')).toBe(true);
    expect(screen.getByTestId('scanner-row-pin').textContent).toBe('Unpin');
    expect(rowClick).not.toHaveBeenCalled();
  });

  it('labels follow the facts: Stop rec is a hold', async () => {
    facts.recording = true;
    render(<ScannerRowActions symbol="QNME" onOpenTrading={() => {}} />);
    expect(screen.queryByTestId('scanner-row-record')).toBeNull();
    const stop = screen.getByTestId('scanner-row-stop-rec');
    expect(stop.getAttribute('aria-label')).toBe('Stop rec');
    vi.useFakeTimers();
    fireEvent.pointerDown(stop, { button: 0 });
    await act(async () => {
      vi.advanceTimersByTime(1300);
    });
    vi.useRealTimers();
    expect(record.stop).toHaveBeenCalledWith('QNME');
  });

  it('★ stars the symbol onto today\'s hot list and reads Listed until pressed again', async () => {
    fakeHotList.reset();
    resetWatchListForTests();
    const rowClick = vi.fn();
    render(
      <div onClick={rowClick}>
        <ScannerRowActions symbol="GRML" onOpenTrading={() => {}} />
      </div>,
    );
    const watch = () => screen.getByTestId('scanner-row-watch');
    expect(watch().textContent).toBe('★');
    await act(async () => { fireEvent.click(watch()); });
    expect(getWatchList()).toEqual(['GRML']);
    expect(fakeHotList.symbols()).toEqual(['GRML']);
    expect(watch().textContent).toBe('★ Listed');
    expect(watch().getAttribute('aria-pressed')).toBe('true');
    await act(async () => { fireEvent.click(watch()); });
    expect(getWatchList()).toEqual([]);
    expect(rowClick).not.toHaveBeenCalled();
    fakeHotList.reset();
    resetWatchListForTests();
  });

  it('states a record failure on the row', async () => {
    record.start.mockResolvedValueOnce('Record start failed');
    render(<ScannerRowActions symbol="VXTL" onOpenTrading={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('scanner-row-record'));
    });
    expect(screen.getByRole('alert').textContent).toBe('Record start failed');
  });
});

describe('ScannerRowMarks', () => {
  beforeEach(() => {
    facts.recording = false;
  });
  afterEach(() => cleanup());

  it('draws nothing when neither fact holds', () => {
    render(<ScannerRowMarks symbol="AAA" />);
    expect(screen.queryByTestId('scanner-row-marks')).toBeNull();
  });

  it('draws the star for a symbol on today\'s hot list, with nothing else true', async () => {
    fakeHotList.reset();
    resetWatchListForTests();
    await act(async () => { addToWatchList('AAA'); });
    render(<ScannerRowMarks symbol="AAA" />);
    expect(screen.getByTestId('watch-mark').getAttribute('title')).toMatch(/AAA is on today's hot list/);
    expect(screen.queryByTestId('scanner-mark-rec')).toBeNull();
    fakeHotList.reset();
    resetWatchListForTests();
  });

  it('draws the REC dot for a recording symbol, and no bot dot (ADR 072)', () => {
    facts.recording = true;
    render(<ScannerRowMarks symbol="GRML" />);
    expect(screen.getByTestId('scanner-mark-rec')).toBeTruthy();
    expect(screen.queryByTestId('scanner-mark-bot')).toBeNull();
  });
});
