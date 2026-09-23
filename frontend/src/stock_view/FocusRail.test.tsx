/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FOCUS_RAIL_STORAGE_KEY } from '../constantGroups/trader_chrome';
import type { AlertObject } from '../hod_momo/types';
import { makeLiveScannerFeedStub, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { ScannerRow } from '../types/scanner';
import { FocusRail } from './FocusRail';
import { focusRowsFor, hodFocusRows, readFocusRailState, stepCursor } from './focusRailState';

const mocks = vi.hoisted(() => ({
  feed: null as LiveScannerFeed | null,
  allow: [] as string[],
  recording: [] as string[],
  live: [] as string[],
  active: 'GRML' as string | null,
  open: vi.fn(),
  scanner: vi.fn(),
  replayDesk: false,
  hod: null as { alerts: AlertObject[]; connected: boolean; feedError: string | null; totalToday: number } | null,
}));

vi.mock('../sim/useSimReplayDesk', () => ({ useSimReplayDesk: () => mocks.replayDesk }));

vi.mock('../scanner/ScannerDataContext', async importOriginal => {
  const actual = await importOriginal<typeof import('../scanner/ScannerDataContext')>();
  return { ...actual, useLiveScannerFeedOptional: () => mocks.feed };
});
vi.mock('../settings/SettingsContext', () => ({ useSettingsOptional: () => null }));
vi.mock('../hod_momo/HodMomoContext', () => ({
  useHodMomoOptional: () => (mocks.hod ? { stream: mocks.hod } : null),
}));
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

/** Fixtures author the gap in percent; the wire carries a fraction (QA V2 / C17). */
const frac = (pct: number | null): number | null => (pct == null ? null : pct / 100);

function row(symbol: string, gap: number, price = 1, hasNews = false): ScannerRow {
  return {
    symbol, price, prev_close: 1, change_pct: frac(gap), change_abs: null, gap_percent: frac(gap), volume: 0, rel_volume: null,
    has_news: hasNews, newest_headline_at: null, market_cap: null, float: null, short_interest: null, short_ratio: null,
  };
}

/** A HOD alert raised at `raised` (epoch s); HOD percents are percent points. */
function alert(ticker: string, strategyId: number, raised: number, extra: Partial<AlertObject> = {}): AlertObject {
  return {
    id: `${raised}-${ticker}-${strategyId}`, timestamp: new Date(raised * 1000).toISOString(), ticker,
    strategy_id: strategyId, strategy_name: 's', price: 1, change_pct: null, rvol: null, float_shares: null,
    gap_pct: null, volume: null, momentum_pct: null, rvol_source: null, consolidation_count: 1,
    consolidated_ids: [], created_ts: raised, ...extra,
  };
}

beforeEach(() => {
  localStorage.clear();
  mocks.hod = { alerts: [], connected: true, feedError: null, totalToday: 0 };
  mocks.feed = makeLiveScannerFeedStub({ gappers: [row('GRML', 131.2, 8.9, true), row('VXTL', 38.2, 3.42), row('CBRX', -5.4, 4.56)] });
  mocks.allow = ['GRML', 'VXTL'];
  mocks.recording = ['GRML'];
  mocks.live = ['GRML'];
  mocks.active = 'GRML';
  mocks.open.mockReset();
  mocks.scanner.mockReset();
  mocks.replayDesk = false;
});
afterEach(cleanup);

describe('FocusRail', () => {
  it('on Sim off the live edge hides today\'s live price, gap and news, and still opens tabs (QA W10)', () => {
    mocks.replayDesk = true;
    render(<FocusRail />);
    expect(screen.getByTestId('focus-rail-replay-note').textContent).toMatch(/live price, gap and news are hidden/);
    const grml = screen.getByTestId('focus-rail-row-GRML');
    expect(grml.textContent).not.toContain('+131%');
    expect(grml.textContent).not.toContain('NEWS');
    expect(grml.textContent).not.toContain('8.90');
    expect(screen.getByTestId('focus-rail-row-CBRX').textContent).not.toContain('no news');
    fireEvent.click(grml);
    expect(mocks.open).toHaveBeenCalledWith('GRML');
  });

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
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'watchlist' } });
    expect(screen.getByTestId('focus-rail-absent').textContent).toMatch(/Watchlist is not mirrored here yet/);
    mocks.feed = null;
    view.rerender(<FocusRail />);
    expect(screen.getByTestId('focus-rail-absent').textContent).toBe('No scanner feed in this window');
  });

  it('mirrors HOD Momo from the HOD stream: one row per ticker, newest raised first, Former Momo off', () => {
    mocks.hod!.alerts = [
      alert('GRML', 2, 100, { price: 8.1, gap_pct: 120.5 }),
      alert('ZZZX', 3, 200, { price: 2.5, gap_pct: 45 }),
      alert('GRML', 5, 300, { price: 8.9, gap_pct: 131.2 }),
      alert('OLDM', 1, 400),
      alert('RUNR', 12, 500, { price: 4, change_pct: 22 }),
    ];
    render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'hod_momo' } });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· HOD Momo 2');
    const rows = screen.getByTestId('focus-rail-rows').querySelectorAll('[role="option"]');
    expect(Array.from(rows).map(r => r.getAttribute('data-testid'))).toEqual(['focus-rail-row-GRML', 'focus-rail-row-ZZZX']);
    const grml = screen.getByTestId('focus-rail-row-GRML');
    expect(grml.textContent).toContain('8.90');
    expect(grml.textContent).toContain('+131%');
    // GRML is on Gappers with news, so the scanner feed supplies its chip.
    expect(grml.textContent).toContain('NEWS');
    // ZZZX is on no scanner list: its news is unknown, never "no news".
    const zzzx = screen.getByTestId('focus-rail-row-ZZZX');
    expect(zzzx.textContent).toContain('+45.0%');
    expect(zzzx.textContent).not.toContain('no news');
    expect(screen.queryByTestId('focus-rail-row-OLDM')).toBeNull();
    fireEvent.click(zzzx);
    expect(mocks.open).toHaveBeenCalledWith('ZZZX');
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'running_up' } });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Running Up 1');
    expect(screen.getByTestId('focus-rail-row-RUNR').textContent).toContain('+22.0%');
  });

  it('the HOD lists name their own stream state and do not need the scanner feed', () => {
    mocks.hod = { alerts: [], connected: false, feedError: null, totalToday: 0 };
    const view = render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'hod_momo' } });
    expect(screen.getByTestId('focus-rail-absent').textContent).toBe('Connecting to the HOD Momo feed');
    mocks.hod = { alerts: [], connected: false, feedError: 'HOD feed closed', totalToday: 0 };
    view.rerender(<FocusRail />);
    expect(screen.getByTestId('focus-rail-absent').textContent).toBe('HOD Momo: HOD feed closed');
    mocks.hod = { alerts: [], connected: true, feedError: null, totalToday: 0 };
    view.rerender(<FocusRail />);
    expect(screen.getByTestId('focus-rail-absent').textContent).toBe('HOD Momo: no rows right now');
    mocks.feed = null;
    mocks.hod = { alerts: [alert('GRML', 2, 100, { price: 8.9 })], connected: true, feedError: null, totalToday: 1 };
    view.rerender(<FocusRail />);
    expect(screen.getByTestId('focus-rail-row-GRML').textContent).toContain('8.90');
    expect(screen.getByTestId('focus-rail-row-GRML').textContent).not.toContain('no news');
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

  it('declares its list for live prices only while its rows are on screen', async () => {
    const setL1FocusTab = vi.fn();
    mocks.feed = makeLiveScannerFeedStub({ setL1FocusTab });
    const view = render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'large_cap' } });
    expect(setL1FocusTab).toHaveBeenLastCalledWith('large_cap');
    view.rerender(<FocusRail active={false} />);
    expect(setL1FocusTab).toHaveBeenLastCalledWith(null);
    view.rerender(<FocusRail active />);
    expect(setL1FocusTab).toHaveBeenLastCalledWith('large_cap');
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-collapse')); });
    expect(setL1FocusTab).toHaveBeenLastCalledWith(null);
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-expand')); });
    expect(setL1FocusTab).toHaveBeenLastCalledWith('large_cap');
    view.unmount();
    expect(setL1FocusTab).toHaveBeenLastCalledWith(null);
  });
});

describe('focusRowsFor / stepCursor', () => {
  it('maps the feed lists and reports unmirrored ones as null', () => {
    const feed = makeLiveScannerFeedStub({ losers: [row('CBRX', -5.4)] });
    expect(focusRowsFor('losers', feed)?.map(r => r.symbol)).toEqual(['CBRX']);
    expect(focusRowsFor('watchlist', feed)).toBeNull();
    expect(focusRowsFor('gappers', null)).toBeNull();
  });

  it('HOD rows say "no news" only for a symbol the scanner feed knows', () => {
    const feed = makeLiveScannerFeedStub({ gappers: [row('CBRX', -5.4)] });
    const rows = hodFocusRows('hod_momo', [alert('CBRX', 2, 2), alert('NEWX', 2, 1)], feed);
    expect(rows.map(r => [r.symbol, r.catalyst, r.newsKnown])).toEqual([['CBRX', null, true], ['NEWX', null, false]]);
  });

  it('steps the cursor within bounds', () => {
    expect(stepCursor(-1, 1, 3)).toBe(0);
    expect(stepCursor(-1, -1, 3)).toBe(2);
    expect(stepCursor(2, 1, 3)).toBe(2);
    expect(stepCursor(0, -1, 3)).toBe(0);
    expect(stepCursor(0, 1, 0)).toBe(-1);
  });
});
