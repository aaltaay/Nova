/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HodMomoContextProvider, type HodMomoContextValue } from '../hod_momo/HodMomoContext';
import type { AlertObject } from '../hod_momo/types';
import type { SetupsBoard } from '../setups';
import type { ScannerRow } from '../types/scanner';
import { setupBoard, setupRow } from './setupFixtures';
import {
  WATCH_LIST_EMPTY,
  WATCH_LIST_NOT_ON_BOARD,
  WATCH_LIST_SETUP_NOT_FOLLOWED,
  WATCH_LIST_SETUP_NOTHING,
  WATCH_LIST_SETUP_OFFLINE_TIP,
  WATCH_LIST_SETUP_UNKNOWN_TIP,
} from './watchListConstants';
import { boardRowsBySymbol, hodAlertsBySymbol, WatchListTab } from './WatchListTab';
import { addToWatchList, getWatchList, resetWatchListForTests } from './watchListStore';
import type { WatchListBoards } from './types';

vi.mock('../bot', () => ({ openBotSymbolMenu: vi.fn(), closeBotSymbolMenu: vi.fn() }));
// The setup scanner's live board, as the provider would hand it over (null: none here).
const setups = vi.hoisted(() => ({ value: null as { board: SetupsBoard | null; connected: boolean } | null }));
vi.mock('../setups', async importOriginal => ({
  ...(await importOriginal<typeof import('../setups')>()),
  useSetupsBoard: () => setups.value,
}));

function row(symbol: string, patch: Partial<ScannerRow> = {}): ScannerRow {
  return {
    symbol,
    price: 4.52,
    prev_close: 3.27,
    change_pct: 0.382,
    change_abs: 1.25,
    gap_percent: 0.2,
    volume: 2_100_000,
    rel_volume: 5.2,
    has_news: false,
    newest_headline_at: null,
    market_cap: null,
    float: null,
    short_interest: null,
    short_ratio: null,
    ...patch,
  };
}

function alert(ticker: string, strategy_id: number, strategy_name: string, created_ts: number): AlertObject {
  return {
    id: `${ticker}-${strategy_id}-${created_ts}`,
    timestamp: new Date(created_ts * 1000).toISOString(),
    created_ts,
    ticker,
    strategy_id,
    strategy_name,
    price: 4.5,
    change_pct: 38,
    rvol: 5,
    float_shares: null,
    gap_pct: null,
    volume: null,
    momentum_pct: null,
    rvol_source: null,
    consolidation_count: 1,
    consolidated_ids: [],
  };
}

const EMPTY: WatchListBoards = { gainers: [], gappers: [], losers: [], afterhours: [], largeCap: [] };
// 10:14:05 and 09:50:00 ET on 2026-09-23, newest first like the stream.
const T1 = Date.UTC(2026, 8, 23, 14, 14, 5) / 1000;
const T0 = Date.UTC(2026, 8, 23, 13, 50, 0) / 1000;
const ALERTS = [
  alert('GRML', 12, 'Running Up', T1 + 60),
  alert('GRML', 1, 'New High of Day', T1),
  alert('GRML', 3, 'Squeeze', T0),
];

function withHod(children: ReactNode, alerts: AlertObject[]) {
  const value = { stream: { alerts, totalToday: alerts.length, connected: true } } as unknown as HodMomoContextValue;
  return <HodMomoContextProvider value={value}>{children}</HodMomoContextProvider>;
}

describe('WatchListTab', () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    setups.value = null;
  });
  afterEach(() => {
    cleanup();
    localStorage.clear();
    resetWatchListForTests();
    setups.value = null;
  });

  it('says how to add a symbol when the list is empty, and adds one by ticker', () => {
    render(<WatchListTab boards={EMPTY} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    expect(screen.getByTestId('watch-list-empty').textContent).toBe(WATCH_LIST_EMPTY);
    const input = screen.getByTestId('watch-list-add-input');
    fireEvent.change(input, { target: { value: 'two words' } });
    fireEvent.submit(screen.getByTestId('watch-list-add'));
    expect(screen.getByRole('alert').textContent).toBe('Not a ticker');
    fireEvent.change(input, { target: { value: 'grml' } });
    fireEvent.submit(screen.getByTestId('watch-list-add'));
    expect(getWatchList()).toEqual(['GRML']);
    expect(screen.getByText('GRML')).toBeTruthy();
  });

  it("shows a board row's facts, today's newest HOD Momo alert, and states what is unknown", () => {
    act(() => {
      addToWatchList('ONCO');
      addToWatchList('GRML');
    });
    const boards = { ...EMPTY, gainers: [row('GRML')] };
    render(withHod(
      <WatchListTab boards={boards} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />,
      ALERTS,
    ));
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    const [grml, onco] = rows;
    expect(grml.textContent).toContain('$4.52');
    expect(grml.textContent).toContain('+38.20%');
    expect(grml.textContent).toContain('Gainers');
    // Running Up counts too: the newest alert is its 10:15:05, three today.
    expect(grml.textContent).toContain('10:15:05 Running Up (3)');
    expect(onco.textContent).toContain(WATCH_LIST_NOT_ON_BOARD);
    expect(onco.textContent).toContain('Not yet today');
  });

  it('never shows a prior-close fallback as a price or a change', () => {
    act(() => { addToWatchList('GRML'); });
    const boards = { ...EMPTY, gappers: [row('GRML', { quote_quality: 'close_fallback' })] };
    render(<WatchListTab boards={boards} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />);
    const grml = screen.getAllByRole('row')[1];
    expect(grml.textContent).not.toContain('$4.52');
    expect(grml.textContent).not.toContain('%');
  });

  it("shows each symbol's most advanced setup, and says why when it has none -- never a guess", () => {
    act(() => { ['ZZZZ', 'PFSA', 'ONCO', 'GRML'].forEach(addToWatchList); });
    const cell = (symbol: string) => screen.getByTestId(`watch-list-setup-${symbol}`);
    // A fresh element each time: the mocked hook is no context, so an equal element would not re-render.
    const tab = () => <WatchListTab boards={EMPTY} selectedSymbol={null} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />;

    // No live board here (disconnected, or the Sim replay on it).
    const { rerender } = render(tab());
    expect(cell('GRML').textContent).toBe('—');
    expect(cell('GRML').getAttribute('data-tip')).toBe(WATCH_LIST_SETUP_OFFLINE_TIP);

    setups.value = {
      connected: true,
      board: setupBoard(
        [setupRow('GRML', 'leg', { setup_type: 'bull_flag', kind: 'bull_flag' }), setupRow('GRML', 'near')],
        { universe_symbols: ['GRML', 'ONCO'] },
      ),
    };
    rerender(tab());
    expect(cell('GRML').textContent).toBe('First pullbackNear+1');
    expect(cell('GRML').getAttribute('data-tip')).toContain('Also: Bull flag Pole');
    expect(cell('ONCO').textContent).toBe(WATCH_LIST_SETUP_NOTHING);
    expect(cell('PFSA').textContent).toBe(WATCH_LIST_SETUP_NOT_FOLLOWED);
    expect(cell('PFSA').getAttribute('data-tip')).toContain('HOD Momo names only');

    // An API from before `universe_symbols` cannot say which it is.
    setups.value = { connected: true, board: setupBoard([], { universe_symbols: undefined }) };
    rerender(tab());
    expect(cell('ONCO').textContent).toBe('—');
    expect(cell('ONCO').getAttribute('data-tip')).toBe(WATCH_LIST_SETUP_UNKNOWN_TIP);
    setups.value = { connected: true, board: setupBoard([setupRow('ONCO', 'armed')], { source: 'sim' }) };
    rerender(tab());
    expect(cell('ONCO').getAttribute('data-tip')).toBe(WATCH_LIST_SETUP_OFFLINE_TIP);
  });

  it('removes a symbol without selecting the row', () => {
    act(() => { addToWatchList('GRML'); });
    const onSelect = vi.fn();
    render(<WatchListTab boards={EMPTY} selectedSymbol={null} onSelectSymbol={onSelect} onOpenTrading={vi.fn()} />);
    fireEvent.click(screen.getByTestId('watch-list-remove-GRML'));
    expect(getWatchList()).toEqual([]);
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe('watch list joins', () => {
  it('takes the first board that holds a symbol, Gainers first', () => {
    const hits = boardRowsBySymbol({ ...EMPTY, gappers: [row('abc', { price: 1 })], gainers: [row('ABC', { price: 2 })] });
    expect(hits.get('ABC')?.board).toBe('Gainers');
    expect(hits.get('ABC')?.row.price).toBe(2);
  });

  it('counts HOD Momo feed alerts per symbol, newest first, Running Up included', () => {
    const byHod = hodAlertsBySymbol(ALERTS);
    expect(byHod.get('GRML')?.count).toBe(3);
    expect(byHod.get('GRML')?.latest.strategy_name).toBe('Running Up');
  });
});
