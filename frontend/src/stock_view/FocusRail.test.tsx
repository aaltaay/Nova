/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FOCUS_RAIL_STORAGE_KEY } from '../constantGroups/trader_chrome';
import { makeLiveScannerFeedStub, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { ScannerRow } from '../types/scanner';
import { FocusRail } from './FocusRail';
import { focusRowsFor, readFocusRailState, stepCursor } from './focusRailState';

const mocks = vi.hoisted(() => ({
  feed: null as LiveScannerFeed | null,
  allow: [] as string[],
  recording: [] as string[],
  live: [] as string[],
  active: 'GRML' as string | null,
  open: vi.fn(),
  scanner: vi.fn(),
}));

vi.mock('../scanner/ScannerDataContext', async importOriginal => {
  const actual = await importOriginal<typeof import('../scanner/ScannerDataContext')>();
  return { ...actual, useLiveScannerFeedOptional: () => mocks.feed };
});
vi.mock('../settings/SettingsContext', () => ({ useSettingsOptional: () => null }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    activeTraderSymbol: mocks.active, traderLiveTabs: mocks.live, openStockView: mocks.open, showScannerView: mocks.scanner,
  }),
}));
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({ symbols: mocks.allow, isAllowed: (s: string) => mocks.allow.includes(s.toUpperCase()) }),
}));
vi.mock('../capture/sessionRecordStore', () => ({
  getRecordingSymbols: () => mocks.recording,
  isTabRecording: (s: string) => mocks.recording.includes(s.toUpperCase()),
  subscribeSessionRecord: () => () => {},
}));

function row(symbol: string, gap: number, price = 1, hasNews = false): ScannerRow {
  return {
    symbol, price, prev_close: 1, change_pct: gap, change_abs: null, gap_percent: gap, volume: 0, rel_volume: null,
    has_news: hasNews, newest_headline_at: null, market_cap: null, float: null, short_interest: null, short_ratio: null,
  };
}

beforeEach(() => {
  localStorage.clear();
  mocks.feed = makeLiveScannerFeedStub({ gappers: [row('GRML', 131.2, 8.9, true), row('VXTL', 38.2, 3.42), row('CBRX', -5.4, 4.56)] });
  mocks.allow = ['GRML', 'VXTL'];
  mocks.recording = ['GRML'];
  mocks.live = ['GRML'];
  mocks.active = 'GRML';
  mocks.open.mockReset();
  mocks.scanner.mockReset();
});
afterEach(cleanup);

describe('FocusRail', () => {
  it('mirrors Gappers with REC and bot dots, highlights the active symbol, and opens on click', () => {
    render(<FocusRail />);
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Gappers 3');
    const grml = screen.getByTestId('focus-rail-row-GRML');
    expect(grml.className).toContain('is-active');
    expect(screen.getByTestId('focus-rail-rec-GRML')).toBeTruthy();
    expect(screen.getByTestId('focus-rail-bot-GRML').getAttribute('data-held')).toBe('1');
    // Allowlisted but no depth line held here: hollow, quiet.
    expect(screen.getByTestId('focus-rail-bot-VXTL').getAttribute('data-held')).toBe('0');
    expect(screen.queryByTestId('focus-rail-bot-CBRX')).toBeNull();
    expect(grml.textContent).toContain('+131%');
    expect(grml.textContent).toContain('NEWS');
    expect(screen.getByTestId('focus-rail-row-CBRX').textContent).toContain('no news');
    fireEvent.click(screen.getByTestId('focus-rail-row-VXTL'));
    expect(mocks.open).toHaveBeenCalledWith('VXTL');
  });

  it('↑ ↓ cycle and Enter opens; the caret picks another list', () => {
    render(<FocusRail />);
    const rail = screen.getByTestId('focus-rail');
    fireEvent.keyDown(rail, { key: 'ArrowDown' });
    fireEvent.keyDown(rail, { key: 'ArrowDown' });
    expect(screen.getByTestId('focus-rail-row-VXTL').className).toContain('is-cursor');
    fireEvent.keyDown(rail, { key: 'Enter' });
    expect(mocks.open).toHaveBeenCalledWith('VXTL');
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'losers' } });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Losers 0');
    expect(screen.getByTestId('focus-rail-absent').textContent).toMatch(/Losers: no rows right now/);
  });

  it('says so when the feed does not carry a list, or when there is no feed at all', () => {
    const view = render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'hod_momo' } });
    expect(screen.getByTestId('focus-rail-absent').textContent).toMatch(/HOD Momo is not mirrored here yet/);
    mocks.feed = null;
    view.rerender(<FocusRail />);
    expect(screen.getByTestId('focus-rail-absent').textContent).toBe('No scanner feed in this window');
  });

  it('persists collapsed state and the mirrored list under the versioned key', async () => {
    render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'gainers' } });
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-collapse')); });
    expect(screen.getByTestId('focus-rail').getAttribute('data-collapsed')).toBe('1');
    expect(JSON.parse(localStorage.getItem(FOCUS_RAIL_STORAGE_KEY) ?? '{}')).toEqual({ v: 1, collapsed: true, list: 'gainers' });
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-expand')); });
    expect(readFocusRailState()).toEqual({ v: 1, collapsed: false, list: 'gainers' });
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ v: 0, collapsed: true, list: 'losers' }));
    expect(readFocusRailState().list).toBe('gappers');
  });
});

describe('focusRowsFor / stepCursor', () => {
  it('maps the feed lists and reports unmirrored ones as null', () => {
    const feed = makeLiveScannerFeedStub({ losers: [row('CBRX', -5.4)] });
    expect(focusRowsFor('losers', feed)?.map(r => r.symbol)).toEqual(['CBRX']);
    expect(focusRowsFor('watchlist', feed)).toBeNull();
    expect(focusRowsFor('gappers', null)).toBeNull();
  });

  it('steps the cursor within bounds', () => {
    expect(stepCursor(-1, 1, 3)).toBe(0);
    expect(stepCursor(-1, -1, 3)).toBe(2);
    expect(stepCursor(2, 1, 3)).toBe(2);
    expect(stepCursor(0, -1, 3)).toBe(0);
    expect(stepCursor(0, 1, 0)).toBe(-1);
  });
});
