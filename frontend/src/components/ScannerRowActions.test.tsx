/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetPinnedRowsForTests, getPinnedRows } from '../scanner/pinnedRowsStore';
import { ScannerRowActions } from './ScannerRowActions';
import { ScannerRowMarks } from './ScannerRowMarks';

const facts = { recording: false, allowlisted: false, depthHeld: false };
vi.mock('./useScannerRowFacts', () => ({
  useScannerRowFacts: () => facts,
}));

const allowlist = { add: vi.fn(async () => null), remove: vi.fn(async () => null) };
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({ symbols: [], isAllowed: () => false, refresh: vi.fn(), ...allowlist }),
}));

const record = { start: vi.fn(async () => null as string | null), stop: vi.fn(async () => null as string | null) };
vi.mock('../capture/sessionRecordStore', () => ({
  startTabRecord: (s: string) => record.start(s),
  stopTabRecord: (s: string) => record.stop(s),
}));

describe('ScannerRowActions', () => {
  beforeEach(() => {
    facts.recording = false;
    facts.allowlisted = false;
    facts.depthHeld = false;
    allowlist.add.mockClear();
    allowlist.remove.mockClear();
    record.start.mockClear();
    record.stop.mockClear();
    _resetPinnedRowsForTests();
  });

  afterEach(() => {
    cleanup();
  });

  it('opens Trader, starts a recording, allowlists and pins -- and never reaches the row', () => {
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
    expect(screen.getByTestId('scanner-row-allowlist').textContent).toBe('Allowlist');
    fireEvent.click(screen.getByTestId('scanner-row-allowlist'));
    expect(allowlist.add).toHaveBeenCalledWith('GRML');
    expect(screen.getByTestId('scanner-row-pin').textContent).toBe('Pin');
    fireEvent.click(screen.getByTestId('scanner-row-pin'));
    expect(getPinnedRows().has('GRML')).toBe(true);
    expect(screen.getByTestId('scanner-row-pin').textContent).toBe('Unpin');
    expect(rowClick).not.toHaveBeenCalled();
  });

  it('labels follow the facts: Stop rec is a hold, Allowlisted removes', async () => {
    facts.recording = true;
    facts.allowlisted = true;
    facts.depthHeld = true;
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
    expect(screen.getByTestId('scanner-row-allowlist').textContent).toBe('Allowlisted ✓');
    fireEvent.click(screen.getByTestId('scanner-row-allowlist'));
    expect(allowlist.remove).toHaveBeenCalledWith('QNME');
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
    facts.allowlisted = false;
    facts.depthHeld = false;
  });
  afterEach(() => cleanup());

  it('draws nothing when neither fact holds', () => {
    render(<ScannerRowMarks symbol="AAA" />);
    expect(screen.queryByTestId('scanner-row-marks')).toBeNull();
  });

  it('draws the REC dot and a filled bot dot for a recording allowlisted symbol', () => {
    facts.recording = true;
    facts.allowlisted = true;
    facts.depthHeld = true;
    render(<ScannerRowMarks symbol="GRML" />);
    expect(screen.getByTestId('scanner-mark-rec')).toBeTruthy();
    expect(screen.getByTestId('scanner-mark-bot').getAttribute('data-held')).toBe('1');
  });

  it('draws a hollow bot dot for an allowlisted symbol with no held line known here', () => {
    facts.allowlisted = true;
    render(<ScannerRowMarks symbol="BRNQ" />);
    expect(screen.queryByTestId('scanner-mark-rec')).toBeNull();
    const bot = screen.getByTestId('scanner-mark-bot');
    expect(bot.getAttribute('data-held')).toBe('0');
    expect(bot.className).toContain('is-quiet');
    expect(bot.getAttribute('title')).toMatch(/no held depth line/);
  });
});
