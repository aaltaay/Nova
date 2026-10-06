/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FOCUS_RAIL_STORAGE_KEY } from '../constantGroups/trader_chrome';
import type { AlertObject } from '../hod_momo/types';
import { makeLiveScannerFeedStub, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { ScannerRow } from '../types/scanner';
import { consumeFocusListRequest, requestFocusList } from '../workspace/focusListRequest';
import { FocusRail } from './FocusRail';
import { focusCardPosition } from './FocusRailHoverCard';
import {
  FOCUS_RAIL_DEFAULT_STATE, followedFocusList, focusRowsFor, readFocusRailState, routeFocusList, stepCursor,
  watchFocusRows, type FocusRow,
} from './focusRailState';
import { focusNewsRank, nextFocusSort, parseFocusSort, sortFocusRows } from './focusRailSort';
import { addToWatchList, resetWatchListForTests } from '../watch_list/watchListStore';

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
  /** The strip menu's strategy picks, shared through the HOD context; null = the default set. */
  visible: null as ReadonlySet<number> | null,
  panel: null as unknown,
}));

// The watch list is today's hot list (ADR 044): an in-memory one here.
vi.mock('../hot_list', async () => (await import('../hot_list/hotListFake')).hotListFakeModule());
vi.mock('../hooks/useCatalystPanel', () => ({
  useCatalystPanel: () => ({ panel: mocks.panel, loading: mocks.panel == null, unavailable: false, error: null }),
}));

vi.mock('../sim/useSimReplayDesk', () => ({ useSimReplayDesk: () => mocks.replayDesk }));

vi.mock('../scanner/ScannerDataContext', async importOriginal => {
  const actual = await importOriginal<typeof import('../scanner/ScannerDataContext')>();
  return { ...actual, useLiveScannerFeedOptional: () => mocks.feed };
});
vi.mock('../settings/SettingsContext', () => ({ useSettingsOptional: () => null }));
// The HOD context as the provider builds it: the stream, its tab counts and the strategy picks.
vi.mock('../hod_momo/HodMomoContext', async () => {
  const { defaultHodMomentumVisibleStrategies, partitionScannerAlerts } = await import('../hod_momo/scannerPartition');
  const { collapseAlertsBySymbol } = await import('../hod_momo/collapseAlertsBySymbol');
  return {
    useHodMomoOptional: () => {
      if (!mocks.hod) return null;
      const { hodMomentum, runningUp } = partitionScannerAlerts(mocks.hod.alerts);
      const visible = mocks.visible ?? defaultHodMomentumVisibleStrategies();
      return {
        stream: mocks.hod,
        config: { state: {} },
        hodCount: collapseAlertsBySymbol(hodMomentum.filter(a => visible.has(a.strategy_id))).length,
        runningUpCount: collapseAlertsBySymbol(runningUp).length,
        visibleStrategies: mocks.visible ?? undefined,
      };
    },
  };
});
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

/** An ISO time `minutes` ago, for the news circle's age. */
const ago = (minutes: number): string => new Date(Date.now() - minutes * 60_000).toISOString();

function row(symbol: string, gap: number, price = 1, headlineAt: string | null = null): ScannerRow {
  return {
    symbol, price, prev_close: 1, change_pct: frac(gap), change_abs: null, gap_percent: frac(gap), volume: 0, rel_volume: null,
    has_news: headlineAt != null, newest_headline_at: headlineAt, market_cap: null, float: null, short_interest: null, short_ratio: null,
  };
}

/** The rail's rows, top to bottom. */
const order = (): string[] => Array.from(screen.getByTestId('focus-rail-rows').querySelectorAll('[role="option"]'))
  .map(r => (r.getAttribute('data-testid') ?? '').replace('focus-rail-row-', ''));

/** A HOD half's strip rows, top to bottom, by symbol. */
const alertOrder = (tid = 'focus-rail'): string[] => Array.from(screen.getByTestId(`${tid}-rows`).querySelectorAll('[role="row"]'))
  .map(r => r.getAttribute('data-symbol') ?? '');

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
  mocks.visible = null;
  mocks.feed = makeLiveScannerFeedStub({ gappers: [row('GRML', 131.2, 8.9, ago(30)), row('VXTL', 38.2, 3.42), row('CBRX', -5.4, 4.56)] });
  mocks.allow = ['GRML', 'VXTL'];
  mocks.recording = ['GRML'];
  mocks.live = ['GRML'];
  mocks.active = 'GRML';
  mocks.open.mockReset();
  mocks.scanner.mockReset();
  mocks.replayDesk = false;
  mocks.panel = null;
  consumeFocusListRequest();
});
afterEach(cleanup);

describe('FocusRail', () => {
  it('on Sim off the live edge hides today\'s live price, gap and news, and still opens tabs (QA W10)', () => {
    mocks.replayDesk = true;
    render(<FocusRail />);
    expect(screen.getByTestId('focus-rail-replay-note').textContent).toMatch(/live price, gap and news are hidden/);
    const grml = screen.getByTestId('focus-rail-row-GRML');
    expect(grml.textContent).not.toContain('+131%');
    expect(grml.textContent).not.toContain('8.90');
    expect(screen.getByTestId('focus-rail-news-GRML').childElementCount).toBe(0);
    expect(screen.getByTestId('focus-rail-news-CBRX').childElementCount).toBe(0);
    expect(screen.getByTestId('focus-rail-sort-symbol')).toBeTruthy();
    expect(screen.queryByTestId('focus-rail-sort-gap')).toBeNull();
    expect(screen.queryByTestId('focus-rail-sort-news')).toBeNull();
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
    // The Scanner's news circle leads the row: red for a headline under 2 h old.
    expect(grml.firstElementChild?.getAttribute('data-testid')).toBe('focus-rail-news-GRML');
    expect(screen.getByTestId('focus-rail-news-GRML').querySelector('.news-flame.flame-hot')).toBeTruthy();
    expect(screen.getByTestId('focus-rail-news-GRML').querySelector('[title]')).toBeNull();
    expect(screen.getByTestId('focus-rail-news-CBRX').textContent).toBe('—');
    fireEvent.click(screen.getByTestId('focus-rail-row-VXTL'));
    expect(mocks.open).toHaveBeenCalledWith('VXTL');
  });

  it('↑ ↓ cycle and Enter opens; the caret picks another list', () => {
    render(<FocusRail />);
    const rail = screen.getByTestId('focus-rail-pane-upper');
    fireEvent.keyDown(rail, { key: 'ArrowDown' });
    fireEvent.keyDown(rail, { key: 'ArrowDown' });
    expect(screen.getByTestId('focus-rail-row-VXTL').className).toContain('is-cursor');
    fireEvent.keyDown(rail, { key: 'Enter' });
    expect(mocks.open).toHaveBeenCalledWith('VXTL');
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'losers' } });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Losers 0');
    expect(screen.getByTestId('focus-rail-absent').textContent).toMatch(/Losers: no rows right now/);
  });

  it('mirrors the watch list in the watch colour, and says so while it is empty', () => {
    resetWatchListForTests();
    render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'watch_list' } });
    expect(screen.getByTestId('focus-rail-absent').textContent).toMatch(/Nothing on your watch list yet/);
    act(() => {
      addToWatchList('VXTL');
      addToWatchList('NOPE');
    });
    expect(order()).toEqual(['NOPE', 'VXTL']);
    expect(screen.getByTestId('focus-rail-watched-VXTL')).toBeTruthy();
    // The ★ beside each starred symbol (operator, 2026-10-06).
    expect(within(screen.getByTestId('focus-rail-watched-VXTL')).getByTestId('watch-mark').dataset.how).toBe('star');
    localStorage.clear();
    resetWatchListForTests();
  });

  it('says so when the feed does not carry a list, or when there is no feed at all', () => {
    const view = render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'watchlist' } });
    expect(screen.getByTestId('focus-rail-absent').textContent).toMatch(/Contenders is not mirrored here yet/);
    mocks.feed = null;
    view.rerender(<FocusRail />);
    expect(screen.getByTestId('focus-rail-absent').textContent).toBe('No scanner feed in this window');
  });

  it("mirrors HOD Momo as the Scanner's strip does, compact: the same batches, newest first, Former Momo off", () => {
    mocks.hod!.alerts = [
      alert('GRML', 2, 100, { price: 8.1, change_pct: 120.5 }),
      alert('ZZZX', 3, 200, { price: 2.5, change_pct: 45 }),
      alert('GRML', 5, 300, { price: 8.9, change_pct: 131.2 }),
      alert('OLDM', 1, 400),
      alert('RUNR', 12, 500, { price: 4, change_pct: 22 }),
    ];
    render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'hod_momo' } });
    // The strip tab's own count; a row per strip row (GRML fired twice, 200 s apart).
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· HOD Momo 2');
    expect(alertOrder()).toEqual(['GRML', 'ZZZX', 'GRML']);
    const [grml] = screen.getAllByTestId('focus-rail-alert-GRML');
    // The strip's cells, compact: time, ticker, the alert's price, its strategy chip.
    expect(grml.querySelector('.hod-strip__time')?.textContent).toMatch(/^\d\d:\d\d:\d\d$/);
    expect(grml.querySelector('.hod-strip__price')?.textContent).toBe('8.90');
    expect(grml.querySelector('.hod-strip__sid')?.textContent).toBe('S5');
    expect(grml.className).toContain('hod-strip__row--compact');
    expect(screen.queryByTestId('focus-rail-alert-OLDM')).toBeNull();
    fireEvent.click(screen.getByTestId('focus-rail-alert-ZZZX'));
    expect(mocks.open).toHaveBeenCalledWith('ZZZX');
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'running_up' } });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Running Up 1');
    expect(screen.getByTestId('focus-rail-alert-RUNR').querySelector('.hod-strip__sid')?.textContent).toBe('S12');
  });

  it("follows the strip menu's strategy picks: one set for both views", () => {
    mocks.hod!.alerts = [alert('GRML', 2, 100), alert('ZZZX', 5, 200)];
    const view = render(<FocusRail />);
    expect(alertOrder('focus-rail-lower')).toEqual(['ZZZX', 'GRML']);
    mocks.visible = new Set([2]);
    view.rerender(<FocusRail />);
    expect(alertOrder('focus-rail-lower')).toEqual(['GRML']);
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
    expect(screen.getByTestId('focus-rail-alert-GRML').querySelector('.hod-strip__price')?.textContent).toBe('8.90');
  });

  it('persists collapsed state and the mirrored list under the versioned key', async () => {
    render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'gainers' } });
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-collapse')); });
    expect(screen.getByTestId('focus-rail').getAttribute('data-collapsed')).toBe('1');
    const lower = { list: 'hod_momo', sort: null, folded: false };
    expect(JSON.parse(localStorage.getItem(FOCUS_RAIL_STORAGE_KEY) ?? '{}')).toEqual({ v: 1, collapsed: true, list: 'gainers', sort: null, lower });
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-expand')); });
    expect(readFocusRailState()).toEqual({ v: 1, collapsed: false, list: 'gainers', sort: null, lower });
    // A v1 file from before sorting reads with no sort, and from before the split with HOD Momo below.
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ v: 1, collapsed: false, list: 'losers' }));
    expect(readFocusRailState().sort).toBeNull();
    expect(readFocusRailState().lower).toEqual(lower);
    // A malformed lower half reads as the default one, field by field.
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ v: 1, list: 'losers', lower: { list: '', sort: 'x', folded: 'yes' } }));
    expect(readFocusRailState().lower).toEqual(lower);
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ v: 1, collapsed: false, list: 'losers', sort: { key: 'vol', dir: 'up' } }));
    expect(readFocusRailState().sort).toBeNull();
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ v: 0, collapsed: true, list: 'losers' }));
    expect(readFocusRailState().list).toBe('gappers');
  });

  it('follows the list a symbol was opened from, including an open made before it mounted', () => {
    mocks.feed = makeLiveScannerFeedStub({ gainers: [row('GNRX', 40, 2)], losers: [row('CBRX', -5.4)] });
    requestFocusList('gainers');
    render(<FocusRail />);
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Gainers 1');
    act(() => { requestFocusList('losers'); });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Losers 1');
    expect(readFocusRailState().list).toBe('losers');
  });

  it('a manual pick holds until the next open from a list; an unmirrored list leaves it as it was', () => {
    render(<FocusRail />);
    act(() => { requestFocusList('gainers'); });
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'afterhours' } });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toMatch(/^· After Hours/);
    act(() => { requestFocusList('watchlist'); });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toMatch(/^· After Hours/);
    // HOD Momo is already on screen in the lower half: neither half moves.
    act(() => { requestFocusList('hod_momo'); });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toMatch(/^· After Hours/);
    expect(screen.getByTestId('focus-rail-lower-list-label').textContent).toMatch(/^HOD Momo/);
    // Running Up takes the lower half, the HOD half; a board list takes the upper.
    act(() => { requestFocusList('running_up'); });
    expect(screen.getByTestId('focus-rail-lower-list-label').textContent).toMatch(/^Running Up/);
    expect(screen.getByTestId('focus-rail-list-label').textContent).toMatch(/^· After Hours/);
    act(() => { requestFocusList('gainers'); });
    expect(screen.getByTestId('focus-rail-list-label').textContent).toMatch(/^· Gainers/);
  });

  it('shows HOD Momo in a lower half that keeps its own list and fold, newest alert first', async () => {
    mocks.hod!.alerts = [
      alert('ZZZX', 3, 200, { price: 2.5, change_pct: 45 }),
      alert('GRML', 5, 300, { price: 8.1, change_pct: 120 }),
    ];
    render(<FocusRail />);
    expect(screen.getByTestId('focus-rail').getAttribute('data-split')).toBe('1');
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Gappers 3');
    expect(screen.getByTestId('focus-rail-lower-list-label').textContent).toBe('HOD Momo 2');
    const lowerOrder = () => alertOrder('focus-rail-lower');
    // Newest alert first; a symbol on both lists shows in both halves.
    expect(lowerOrder()).toEqual(['GRML', 'ZZZX']);
    expect(screen.getByTestId('focus-rail-row-GRML')).toBeTruthy();
    // An alert list does not sort (operator decision 2026-09-24): its column
    // labels say so, and the newest cross stays on top.
    expect(screen.getByTestId('focus-rail-lower-cols').getAttribute('title')).toMatch(/^Newest high-of-day cross first/);
    expect(screen.queryByTestId('focus-rail-lower-sort-symbol')).toBeNull();
    expect(readFocusRailState().lower.sort).toBeNull();
    // The upper half still sorts on its own.
    fireEvent.click(screen.getByTestId('focus-rail-sort-symbol'));
    expect(order()).toEqual(['CBRX', 'GRML', 'VXTL']);
    expect(readFocusRailState().sort).toEqual({ key: 'symbol', dir: 'asc' });
    // ↑ ↓ and Enter work in the half that has the keys.
    const lowerPane = screen.getByTestId('focus-rail-pane-lower');
    fireEvent.keyDown(lowerPane, { key: 'ArrowDown' });
    fireEvent.keyDown(lowerPane, { key: 'Enter' });
    expect(mocks.open).toHaveBeenCalledWith('GRML');
    // Its caret picks another list for the lower half only.
    fireEvent.change(screen.getByTestId('focus-rail-lower-pick'), { target: { value: 'running_up' } });
    expect(screen.getByTestId('focus-rail-lower-list-label').textContent).toBe('Running Up 0');
    expect(screen.getByTestId('focus-rail-list-label').textContent).toBe('· Gappers 3');
    // Folding leaves its header; the upper half takes the height.
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-lower-fold')); });
    expect(screen.getByTestId('focus-rail-pane-lower').getAttribute('data-folded')).toBe('1');
    expect(screen.queryByTestId('focus-rail-lower-rows')).toBeNull();
    expect(screen.getByTestId('focus-rail').getAttribute('data-split')).toBe('0');
    expect(readFocusRailState().lower).toEqual({ list: 'running_up', sort: null, folded: true });
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-lower-fold')); });
    expect(screen.getByTestId('focus-rail-lower-rows')).toBeTruthy();
  });

  it('a sort saved on a HOD half before is ignored: the newest alert stays on top', () => {
    mocks.hod!.alerts = [
      alert('ZZZX', 3, 200, { price: 2.5, change_pct: 45 }),
      alert('GRML', 5, 300, { price: 8.1, change_pct: 120 }),
    ];
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({
      v: 1, collapsed: false, list: 'gappers', lower: { list: 'hod_momo', sort: { key: 'symbol', dir: 'desc' }, folded: false },
    }));
    render(<FocusRail />);
    expect(alertOrder('focus-rail-lower')).toEqual(['GRML', 'ZZZX']);
  });

  it("a HOD row shows the strip's price -- the alert's print -- whatever a board says now", () => {
    mocks.hod!.alerts = [alert('PFSA', 3, 100, { price: 4.38 })];
    mocks.feed = makeLiveScannerFeedStub({ gainers: [row('PFSA', 70.2, 3.48)] });
    render(<FocusRail />);
    expect(screen.getByTestId('focus-rail-lower-alert-PFSA').querySelector('.hod-strip__price')?.textContent).toBe('4.38');
  });

  it('declares its lists for live prices only while their rows are on screen', async () => {
    const setL1FocusTabs = vi.fn();
    mocks.feed = makeLiveScannerFeedStub({ setL1FocusTabs });
    const view = render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'large_cap' } });
    // HOD Momo below is an alert list: it takes no price patches, so it is not declared.
    expect(setL1FocusTabs).toHaveBeenLastCalledWith(['large_cap']);
    fireEvent.change(screen.getByTestId('focus-rail-lower-pick'), { target: { value: 'gainers' } });
    expect(setL1FocusTabs).toHaveBeenLastCalledWith(['large_cap', 'gainers']);
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-lower-fold')); });
    expect(setL1FocusTabs).toHaveBeenLastCalledWith(['large_cap']);
    view.rerender(<FocusRail active={false} />);
    expect(setL1FocusTabs).toHaveBeenLastCalledWith([]);
    view.rerender(<FocusRail active />);
    expect(setL1FocusTabs).toHaveBeenLastCalledWith(['large_cap']);
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-collapse')); });
    expect(setL1FocusTabs).toHaveBeenLastCalledWith([]);
    await act(async () => { fireEvent.click(screen.getByTestId('focus-rail-expand')); });
    expect(setL1FocusTabs).toHaveBeenLastCalledWith(['large_cap']);
    view.unmount();
    expect(setL1FocusTabs).toHaveBeenLastCalledWith([]);
  });

  it('sorts by a column header: first click, flip, then back to the list order -- remembered', () => {
    const view = render(<FocusRail />);
    expect(order()).toEqual(['GRML', 'VXTL', 'CBRX']);
    fireEvent.click(screen.getByTestId('focus-rail-sort-gap'));
    expect(order()).toEqual(['GRML', 'VXTL', 'CBRX']);
    expect(screen.getByTestId('focus-rail-sort-gap').getAttribute('data-dir')).toBe('desc');
    fireEvent.click(screen.getByTestId('focus-rail-sort-gap'));
    expect(order()).toEqual(['CBRX', 'VXTL', 'GRML']);
    expect(screen.getByTestId('focus-rail-sort-gap').getAttribute('aria-sort')).toBe('ascending');
    fireEvent.click(screen.getByTestId('focus-rail-sort-symbol'));
    expect(order()).toEqual(['CBRX', 'GRML', 'VXTL']);
    expect(readFocusRailState().sort).toEqual({ key: 'symbol', dir: 'asc' });
    view.unmount();
    render(<FocusRail />);
    expect(order()).toEqual(['CBRX', 'GRML', 'VXTL']);
    fireEvent.click(screen.getByTestId('focus-rail-sort-symbol'));
    fireEvent.click(screen.getByTestId('focus-rail-sort-symbol'));
    expect(order()).toEqual(['GRML', 'VXTL', 'CBRX']);
    expect(readFocusRailState().sort).toBeNull();
  });

  it('the news header puts news first, freshest first, ties by the biggest %', () => {
    mocks.feed = makeLiveScannerFeedStub({ gainers: [
      row('AAAA', 50), row('OLDN', 10, 1, ago(600)), row('BBBB', 80), row('HOTN', 5, 1, ago(20)), row('HOT2', 30, 1, ago(40)),
    ] });
    render(<FocusRail />);
    fireEvent.change(screen.getByTestId('focus-rail-pick'), { target: { value: 'gainers' } });
    fireEvent.click(screen.getByTestId('focus-rail-sort-news'));
    expect(order()).toEqual(['HOT2', 'HOTN', 'OLDN', 'BBBB', 'AAAA']);
  });

  it('a stored %-sort does not reorder a Sim replay desk, which shows no live %', () => {
    localStorage.setItem(FOCUS_RAIL_STORAGE_KEY, JSON.stringify({ v: 1, collapsed: false, list: 'gappers', sort: { key: 'gap', dir: 'asc' } }));
    mocks.replayDesk = true;
    render(<FocusRail />);
    expect(order()).toEqual(['GRML', 'VXTL', 'CBRX']);
  });

  it('hovering the news circle opens the news beside the rail; leaving the row closes it', () => {
    vi.useFakeTimers();
    try {
      mocks.panel = {
        schema_version: 1, symbol: 'GRML', generated_at: 0, window_start: 0, items_total: 2,
        verdict: {
          verdict: 'catalyst', category: 'contract', strength: 'strong', title: 'GRML wins a Navy contract', source: 'globenewswire',
          published_ts: Date.now() / 1000 - 1800, url: null, negative_too: false, rules_version: 'v6',
        },
        items: [
          { item_id: 'a', source: 'globenewswire', publisher: null, published_ts: Date.now() / 1000 - 1800, title: 'GRML wins a Navy contract',
            url: null, kind: 'catalyst', category: 'contract', strength: 'strong', dilution: false },
          { item_id: 'b', source: 'alpaca', publisher: 'Benzinga', published_ts: Date.now() / 1000 - 600, title: '12 stocks moving',
            url: null, kind: 'noise', category: 'movers_list', strength: null, dilution: false },
        ],
      };
      render(<FocusRail />);
      fireEvent.mouseEnter(screen.getByTestId('focus-rail-news-GRML'));
      const card = screen.getByTestId('focus-rail-card');
      const news = screen.getByTestId('focus-rail-card-news');
      expect(news.textContent).toContain('GRML · News since the prior close');
      expect(news.textContent).toContain('GRML wins a Navy contract');
      expect(news.textContent).toContain('1 movers lists / market wraps hidden');
      // One card: GRML's REC / bot status sits under its news, not in a second card.
      expect(card.contains(screen.getByTestId('focus-rail-card-status'))).toBe(true);
      // Crossing the dots on the way to the card keeps the news on screen.
      fireEvent.mouseEnter(screen.getByTestId('focus-rail-dots-GRML'));
      expect(screen.getAllByTestId('focus-rail-card')).toHaveLength(1);
      expect(screen.getByTestId('focus-rail-card-news').textContent).toContain('GRML wins a Navy contract');
      // Moving into the card keeps it; leaving the row and the card closes it.
      fireEvent.mouseLeave(screen.getByTestId('focus-rail-row-GRML'));
      fireEvent.mouseEnter(screen.getByTestId('focus-rail-card'));
      act(() => { vi.advanceTimersByTime(500); });
      expect(screen.getByTestId('focus-rail-card-news')).toBeTruthy();
      fireEvent.mouseLeave(screen.getByTestId('focus-rail-card'));
      act(() => { vi.advanceTimersByTime(500); });
      expect(screen.queryByTestId('focus-rail-card')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('hovering the REC / bot dots opens the same card: the news, then what the dots mean', () => {
    render(<FocusRail />);
    fireEvent.mouseEnter(screen.getByTestId('focus-rail-dots-GRML'));
    const status = screen.getByTestId('focus-rail-card-status');
    expect(screen.getByTestId('focus-rail-card-news').textContent).toContain('GRML · News since the prior close');
    expect(status.textContent).toMatch(/^Status/);
    expect(screen.getByTestId('focus-rail-card-rec').textContent).toMatch(/recording this symbol's tape and Level 2/);
    expect(screen.getByTestId('focus-rail-card-bot').getAttribute('data-held')).toBe('1');
    expect(status.textContent).toMatch(/so the bot can see it/);
    fireEvent.mouseEnter(screen.getByTestId('focus-rail-dots-VXTL'));
    expect(screen.getAllByTestId('focus-rail-card')).toHaveLength(1);
    expect(screen.getByTestId('focus-rail-card-news').textContent).toContain('VXTL · News since the prior close');
    expect(screen.getByTestId('focus-rail-card-bot').getAttribute('data-held')).toBe('0');
    expect(screen.getByTestId('focus-rail-card-status').textContent).toMatch(/cannot act on it/);
    expect(screen.queryByTestId('focus-rail-card-rec')).toBeNull();
    // A row with no dots has no status section.
    fireEvent.mouseEnter(screen.getByTestId('focus-rail-news-CBRX'));
    expect(screen.getByTestId('focus-rail-card-news').textContent).toContain('CBRX');
    expect(screen.queryByTestId('focus-rail-card-status')).toBeNull();
  });

  it('on a Sim replay desk the card keeps the status and leaves today\'s news out', () => {
    mocks.replayDesk = true;
    render(<FocusRail />);
    fireEvent.mouseEnter(screen.getByTestId('focus-rail-news-GRML'));
    expect(screen.queryByTestId('focus-rail-card')).toBeNull();
    fireEvent.mouseEnter(screen.getByTestId('focus-rail-dots-GRML'));
    expect(screen.queryByTestId('focus-rail-card-news')).toBeNull();
    expect(screen.getByTestId('focus-rail-card-status').textContent).toMatch(/^GRML · Status/);
    // No dots and no news: nothing to show.
    fireEvent.mouseEnter(screen.getByTestId('focus-rail-dots-CBRX'));
    expect(screen.getByTestId('focus-rail-card-status').textContent).toMatch(/^GRML/);
  });
});

describe('focusRowsFor / stepCursor', () => {
  it('maps the feed lists and reports unmirrored ones as null', () => {
    const feed = makeLiveScannerFeedStub({ losers: [row('CBRX', -5.4)] });
    expect(focusRowsFor('losers', feed)?.map(r => r.symbol)).toEqual(['CBRX']);
    expect(focusRowsFor('watchlist', feed)).toBeNull();
    expect(focusRowsFor('gappers', null)).toBeNull();
  });

  it("shows the Scanner's %, never the opening gap, on After Hours (2026-10-05)", () => {
    // OLOX opened at 0.85 on a 0.8415 prior close (+1.0% gap) and traded 1.20 after hours (+42.6%).
    const olox: ScannerRow = { ...row('OLOX', 1, 1.2), change_pct: 0.426, gap_percent: 0.0101 };
    const feed = makeLiveScannerFeedStub({ afterhours: [olox] });
    expect(focusRowsFor('afterhours', feed)?.[0].changePct).toBeCloseTo(42.6, 6);
    // A row priced at IBKR's prior close (no trade yet) has no move, as on the Scanner.
    const fallback: ScannerRow = { ...row('NOTR', 0, 2), quote_quality: 'close_fallback' };
    expect(focusRowsFor('gainers', makeLiveScannerFeedStub({ gainers: [fallback] }))?.[0].changePct).toBeNull();
  });

  it('watch list rows keep the list order, take facts from the board that holds them, and invent none', () => {
    const feed = makeLiveScannerFeedStub({ losers: [row('CBRX', -5.4)] });
    const rows = watchFocusRows(['NOPE', 'CBRX'], feed);
    expect(rows.map(r => r.symbol)).toEqual(['NOPE', 'CBRX']);
    expect(rows[0]).toEqual({ symbol: 'NOPE', price: null, changePct: null, headlineAt: null, newsKnown: false });
    expect(rows[1].changePct).toBe(-5.4);
    expect(watchFocusRows(['NOPE'], null)[0].price).toBeNull();
  });

  it('routes a followed list to the half that shows its kind', () => {
    const base = FOCUS_RAIL_DEFAULT_STATE;
    expect(routeFocusList(base, 'gappers')).toBeNull();
    expect(routeFocusList(base, 'hod_momo')).toBeNull();
    expect(routeFocusList(base, 'gainers')).toEqual({ list: 'gainers' });
    expect(routeFocusList(base, 'running_up')).toEqual({ lower: { ...base.lower, list: 'running_up' } });
    expect(routeFocusList(base, 'watchlist')).toBeNull();
    // A lower half on a board list, or folded away, leaves the HOD lists to the upper half.
    expect(routeFocusList({ ...base, lower: { ...base.lower, list: 'losers' } }, 'running_up')).toEqual({ list: 'running_up' });
    expect(routeFocusList({ ...base, lower: { ...base.lower, folded: true } }, 'hod_momo')).toEqual({ list: 'hod_momo' });
  });

  it('follows only a list the rail mirrors', () => {
    expect(followedFocusList('watch_list')).toBe('watch_list');
    expect(followedFocusList('gainers')).toBe('gainers');
    expect(followedFocusList('running_up')).toBe('running_up');
    expect(followedFocusList('watchlist')).toBeNull();
    expect(followedFocusList(null)).toBeNull();
  });

  it('steps the cursor within bounds', () => {
    expect(stepCursor(-1, 1, 3)).toBe(0);
    expect(stepCursor(-1, -1, 3)).toBe(2);
    expect(stepCursor(2, 1, 3)).toBe(2);
    expect(stepCursor(0, -1, 3)).toBe(0);
    expect(stepCursor(0, 1, 0)).toBe(-1);
  });
});

describe('focus rail sorting and the hover card position', () => {
  const focusRow = (symbol: string, patch: Partial<FocusRow> = {}): FocusRow => ({
    symbol, price: 1, changePct: 0, headlineAt: null, newsKnown: true, ...patch,
  });

  it('cycles a column: its first direction, flipped, then none', () => {
    expect(nextFocusSort(null, 'gap')).toEqual({ key: 'gap', dir: 'desc' });
    expect(nextFocusSort({ key: 'gap', dir: 'desc' }, 'gap')).toEqual({ key: 'gap', dir: 'asc' });
    expect(nextFocusSort({ key: 'gap', dir: 'asc' }, 'gap')).toBeNull();
    expect(nextFocusSort(null, 'symbol')).toEqual({ key: 'symbol', dir: 'asc' });
    expect(nextFocusSort({ key: 'symbol', dir: 'asc' }, 'price')).toEqual({ key: 'price', dir: 'desc' });
    expect(parseFocusSort({ key: 'news', dir: 'desc' })).toEqual({ key: 'news', dir: 'desc' });
    expect(parseFocusSort('gap')).toBeNull();
  });

  it('keeps an unknown value last in either direction, never read as zero', () => {
    const rows = [focusRow('NULL', { price: null }), focusRow('LOW', { price: 1 }), focusRow('HIGH', { price: 9 })];
    expect(sortFocusRows(rows, { key: 'price', dir: 'desc' }).map(r => r.symbol)).toEqual(['HIGH', 'LOW', 'NULL']);
    expect(sortFocusRows(rows, { key: 'price', dir: 'asc' }).map(r => r.symbol)).toEqual(['LOW', 'HIGH', 'NULL']);
    expect(sortFocusRows(rows, null)).toBe(rows);
  });

  it('ranks news the way the circle reads: catalyst by age, bad news, nothing, unknown', () => {
    const now = Date.UTC(2026, 8, 23, 14);
    const verdict = (patch: object) => ({
      verdict: 'catalyst', category: 'contract', strength: 'strong', title: 't', source: 'edgar', published_ts: now / 1000 - 600,
      url: null, negative_too: false, rules_version: 'v6', ...patch,
    }) as FocusRow['verdict'];
    const hot = focusNewsRank(focusRow('A', { verdict: verdict({}) }), now)!;
    const cool = focusNewsRank(focusRow('B', { verdict: verdict({ published_ts: now / 1000 - 20 * 3600 }) }), now)!;
    const negative = focusNewsRank(focusRow('C', { verdict: verdict({ verdict: 'negative', category: 'offering' }) }), now)!;
    const none = focusNewsRank(focusRow('D', { verdict: verdict({ verdict: 'none_found' }) }), now)!;
    expect(hot).toBeGreaterThan(cool);
    expect(cool).toBeGreaterThan(negative);
    expect(negative).toBeGreaterThan(none);
    expect(focusNewsRank(focusRow('E', { verdict: null }), now)).toBeNull();
    expect(focusNewsRank(focusRow('F', { newsKnown: false }), now)).toBeNull();
  });

  it('places the card right of the row, or left when the screen ends', () => {
    const anchor = { left: 50, top: 100, right: 270, bottom: 124 };
    expect(focusCardPosition(anchor, { width: 320, height: 200 }, { width: 1200, height: 800 })).toEqual({ left: 278, top: 100 });
    expect(focusCardPosition(anchor, { width: 320, height: 200 }, { width: 500, height: 800 }).left).toBe(8);
    expect(focusCardPosition({ ...anchor, top: 750 }, { width: 320, height: 200 }, { width: 1200, height: 800 }).top).toBe(592);
  });
});
