/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DESK_BOARD_STORAGE_KEY } from '../constantGroups/desk';
import { makeLiveScannerFeedStub, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { ScannerRow } from '../types/scanner';
import {
  resetNavRailStoreForTests,
  setNavPage,
} from '../workspace/navRailStore';
import { DeskPage } from './DeskPage';

const mocks = vi.hoisted(() => ({
  feed: null as LiveScannerFeed | null,
  sample: null as object | null,
  tabs: [] as string[],
  live: [] as string[],
  active: null as string | null,
  selected: null as string | null,
  status: { capture: true, recording: true, capture_symbols: ['GRML'] } as Record<string, unknown>,
  allow: ['GRML'] as string[],
  openTraderTab: vi.fn(),
  openStockView: vi.fn(),
  startRecord: vi.fn(async () => null),
  stopRecord: vi.fn(async () => null),
  allowAdd: vi.fn(async () => null),
  allowRemove: vi.fn(async () => null),
  publish: vi.fn(),
  dockProps: null as Record<string, unknown> | null,
  bridgeProps: null as Record<string, unknown> | null,
}));

vi.mock('../scanner/ScannerDataContext', async importOriginal => {
  const actual = await importOriginal<typeof import('../scanner/ScannerDataContext')>();
  return { ...actual, useLiveScannerFeedOptional: () => mocks.feed };
});
vi.mock('../sample_data/SampleDataContext', () => ({ useSampleDataOptional: () => mocks.sample }));
vi.mock('../settings/SettingsContext', () => ({ useSettingsOptional: () => null }));
vi.mock('../workspace/useModuleVisibility', () => ({ useModuleVisibility: () => ({ visibility: {} }) }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    traderTabs: mocks.tabs, traderLiveTabs: mocks.live, activeTraderSymbol: mocks.active, selectedSymbol: mocks.selected,
    openTraderTab: mocks.openTraderTab, openStockView: mocks.openStockView,
  }),
}));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => mocks.status }));
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({
    symbols: mocks.allow, isAllowed: (s: string) => mocks.allow.includes(s.toUpperCase()), add: mocks.allowAdd, remove: mocks.allowRemove,
  }),
}));
vi.mock('../capture/sessionRecordStore', () => ({ startTabRecord: mocks.startRecord, stopTabRecord: mocks.stopRecord }));
vi.mock('../hod_momo/usePublishScannerNews', () => ({ usePublishScannerNews: mocks.publish }));
vi.mock('../hod_momo/HodMomoDock', () => ({
  HodMomoDock: (props: Record<string, unknown>) => { mocks.dockProps = props; return <div data-testid="hod-momo-dock" />; },
}));
vi.mock('../components/ScannerBarBridge', () => ({
  ScannerBarBridge: (props: Record<string, unknown>) => { mocks.bridgeProps = props; return null; },
}));

function row(symbol: string, gap: number): ScannerRow {
  return {
    symbol, price: 1, prev_close: 1, change_pct: gap, change_abs: null, gap_percent: gap, volume: 0, rel_volume: null,
    has_news: false, newest_headline_at: null, market_cap: null, float: null, short_interest: null, short_ratio: null,
  };
}

beforeEach(() => {
  localStorage.clear();
  resetNavRailStoreForTests();
  setNavPage('desk');
  mocks.feed = makeLiveScannerFeedStub({ gappers: [row('GRML', 33.3), row('VXTL', 21.7)], losers: [row('CBRX', -5.4)], setL1ActiveTab: vi.fn() });
  mocks.sample = null;
  mocks.tabs = [];
  mocks.live = [];
  mocks.active = null;
  mocks.selected = null;
  mocks.status = { capture: true, recording: true, capture_symbols: ['GRML'] };
  mocks.allow = ['GRML'];
  mocks.openTraderTab.mockReset();
  mocks.openStockView.mockReset();
  mocks.startRecord.mockClear();
  mocks.stopRecord.mockClear();
  mocks.allowAdd.mockClear();
  mocks.allowRemove.mockClear();
  mocks.publish.mockReset();
  mocks.dockProps = null;
  mocks.bridgeProps = null;
});
afterEach(cleanup);

describe('DeskPage', () => {
  it('mounts the Scanner dock over the board, says the workspace is empty, and a row click opens the tab in place', () => {
    render(<DeskPage />);
    expect(screen.getByTestId('desk-page')).toBeTruthy();
    expect(screen.getByTestId('hod-momo-dock')).toBeTruthy();
    // The dock's ticker button opens beside the board, not the full Trader.
    expect(mocks.dockProps?.onOpenTrading).toBe(mocks.openTraderTab);
    expect(screen.getByTestId('desk-board')).toBeTruthy();
    expect(screen.getByTestId('desk-workspace-empty').textContent).toMatch(/No symbol open/);
    fireEvent.click(screen.getByTestId('desk-board-row-VXTL'));
    expect(mocks.openTraderTab).toHaveBeenCalledWith('VXTL');
    expect(mocks.openStockView).not.toHaveBeenCalled();
    fireEvent.doubleClick(screen.getByTestId('desk-board-row-VXTL'));
    expect(mocks.openStockView).toHaveBeenCalledWith('VXTL');
  });

  it('highlights the active tab as the board row, hides the empty note, and shows REC / bot dots from status + allowlist', () => {
    mocks.tabs = ['GRML'];
    mocks.live = ['GRML'];
    mocks.active = 'GRML';
    render(<DeskPage />);
    expect(screen.queryByTestId('desk-workspace-empty')).toBeNull();
    expect(screen.getByTestId('desk-board-row-GRML').getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('desk-board-rec-GRML')).toBeTruthy();
    expect(screen.getByTestId('desk-board-bot-GRML').getAttribute('data-held')).toBe('1');
    expect(screen.queryByTestId('desk-board-rec-VXTL')).toBeNull();
  });

  it('declares the board list for L1, bridges the header, publishes scanner news, and persists the picked list', () => {
    render(<DeskPage />);
    expect(mocks.feed!.setL1ActiveTab).toHaveBeenCalledWith('gappers');
    expect(mocks.bridgeProps?.activeTab).toBe('gappers');
    expect(mocks.publish).toHaveBeenCalledWith(expect.objectContaining({ source: 'live', gappers: mocks.feed!.gappers, clear: false }));
    fireEvent.change(screen.getByTestId('desk-board-pick'), { target: { value: 'losers' } });
    expect(mocks.feed!.setL1ActiveTab).toHaveBeenLastCalledWith('losers');
    expect(screen.getByTestId('desk-board-row-CBRX')).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(DESK_BOARD_STORAGE_KEY)!)).toEqual({ v: 1, list: 'losers' });
    cleanup();
    render(<DeskPage />);
    expect(screen.getByTestId('desk-board-list-label').textContent).toBe('Losers');
  });

  it('hover Record / Allowlist call the capture store and the bot allowlist', () => {
    render(<DeskPage />);
    fireEvent.click(screen.getByTestId('desk-board-record-GRML'));
    expect(mocks.stopRecord).toHaveBeenCalledWith('GRML');
    fireEvent.click(screen.getByTestId('desk-board-record-VXTL'));
    expect(mocks.startRecord).toHaveBeenCalledWith('VXTL');
    fireEvent.click(screen.getByTestId('desk-board-allowlist-GRML'));
    expect(mocks.allowRemove).toHaveBeenCalledWith('GRML');
    fireEvent.click(screen.getByTestId('desk-board-allowlist-VXTL'));
    expect(mocks.allowAdd).toHaveBeenCalledWith('VXTL');
    expect(mocks.openTraderTab).not.toHaveBeenCalled();
  });

  it('says so with no scanner feed and is a stated absence in Sample Data mode', () => {
    mocks.feed = null;
    const view = render(<DeskPage />);
    expect(screen.getByTestId('desk-board-absent').textContent).toBe('No scanner feed in this window');
    expect(mocks.bridgeProps).toBeNull();
    mocks.sample = {};
    view.rerender(<DeskPage />);
    expect(screen.getByTestId('desk-page').textContent).toBe('Desk is not available in Sample Data mode.');
    expect(screen.queryByTestId('desk-board')).toBeNull();
  });
});
