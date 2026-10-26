/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DESK_POLL_SNAP_KEY_PREFIX } from '../constantGroups/global_bar';
import { TOP_NINE_LIST_KEY, TOP_NINE_NO_DESK, TOP_NINE_OPEN_WAIT_MS, TOP_NINE_SHARE, TOP_NINE_VIEWER_KEY } from './topNineConstants';
import { TOP_NINE_SCHEMA_VERSION, type TopNineRow, type TopNineSnapshot } from './topNineSnapshot';

const requestOpenOnDesk = vi.fn(async (_symbol: string, _opts: { from?: string; waitMs: number }) => false);
vi.mock('../workspace', () => ({ requestOpenOnDesk: (s: string, o: { from?: string; waitMs: number }) => requestOpenOnDesk(s, o) }));

import TopNineApp from './TopNineApp';

function board(symbols: string[]): TopNineRow[] {
  return symbols.map((symbol, i) => ({
    symbol, rank: i + 1, changePct: 30 - i, price: 2, volume: 5_800_000, float: 81_400, halted: symbol === 'SMX',
  }));
}

function snap(gainers: string[]): TopNineSnapshot {
  return {
    schema_version: TOP_NINE_SCHEMA_VERSION,
    source: { kind: 'live' },
    asOf: 1_792_160_040,
    lists: {
      gappers: { rows: [], total: 14 },
      gainers: { rows: board(gainers), total: 50 },
      afterhours: { rows: [], total: 0 },
    },
  };
}

const KEY = `${DESK_POLL_SNAP_KEY_PREFIX}${TOP_NINE_SHARE}`;
const AT_1013 = ['XLAB', 'WORX', 'ZTG', 'SMX', 'FVNNU', 'SGRX', 'TCRT', 'SITC', 'CORD'];
const AT_1014 = ['XLAB', 'ZTG', 'SMX', 'FVNNU', 'WORX', 'SGRX', 'TCRT', 'SITC', 'CORD'];

function send(s: TopNineSnapshot) {
  const env = JSON.stringify({ ts: Date.now(), payload: s });
  localStorage.setItem(KEY, env);
  window.dispatchEvent(new StorageEvent('storage', { key: KEY, newValue: env }));
}

describe('TopNineApp', () => {
  beforeEach(() => {
    localStorage.clear();
    requestOpenOnDesk.mockClear();
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ bars: [] }), { status: 200 })));
    localStorage.setItem(KEY, JSON.stringify({ ts: Date.now(), payload: snap(AT_1013) }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows the desk\'s first nine Gainers, ranked as sent, and beats so the desk keeps sending', () => {
    render(<TopNineApp />);
    const tiles = screen.getAllByTestId(/^top-nine-tile-/);
    expect(tiles.map((t) => t.getAttribute('data-testid'))).toEqual(AT_1013.map((s) => `top-nine-tile-${s}`));
    expect(screen.getByTestId('top-nine-tile-ZTG').getAttribute('data-rank')).toBe('3');
    expect(screen.getByTestId('top-nine-tile-SMX').textContent).toContain('HALTED');
    expect(screen.getByTestId('top-nine-tab-gainers').textContent).toBe('Gainers50');
    expect(Number(localStorage.getItem(TOP_NINE_VIEWER_KEY))).toBeGreaterThan(0);
    // Nothing moved yet: the first board is never marked.
    expect(screen.queryByTestId(/^top-nine-pill-/)).toBeNull();
  });

  it('lights up each stock that changed rank, and logs the switch', () => {
    render(<TopNineApp />);
    act(() => send(snap(AT_1014)));
    expect(screen.getByTestId('top-nine-tile-ZTG').getAttribute('data-mark')).toBe('up');
    expect(screen.getByTestId('top-nine-pill-ZTG').textContent).toBe('▲ 3 → 2');
    expect(screen.getByTestId('top-nine-tile-WORX').getAttribute('data-mark')).toBe('down');
    expect(screen.getByTestId('top-nine-pill-WORX').textContent).toBe('▼ 2 → 5');
    expect(screen.getByTestId('top-nine-tile-XLAB').getAttribute('data-mark')).toBe('none');
    expect(screen.getByTestId('top-nine-log').textContent).toContain('WORX ▼2→5');
  });

  it('asks the desk to open a double-clicked stock in its Trader, and says so when no desk answers', async () => {
    render(<TopNineApp />);
    await act(async () => {
      fireEvent.doubleClick(screen.getByTestId('top-nine-tile-ZTG'));
    });
    expect(requestOpenOnDesk).toHaveBeenCalledWith('ZTG', { from: 'gainers', waitMs: TOP_NINE_OPEN_WAIT_MS });
    expect(screen.getByTestId('top-nine-notice').textContent).toBe(TOP_NINE_NO_DESK);
  });

  it('follows the list a rail button chose', () => {
    render(<TopNineApp />);
    act(() => {
      localStorage.setItem(TOP_NINE_LIST_KEY, JSON.stringify({ schema_version: 1, value: 'afterhours' }));
      window.dispatchEvent(new StorageEvent('storage', { key: TOP_NINE_LIST_KEY }));
    });
    expect(screen.getByTestId('top-nine-app').getAttribute('data-list')).toBe('afterhours');
    expect(screen.getByTestId('top-nine-empty').textContent).toContain('4:01 PM');
  });

  it('never shows a board a closed desk left behind', () => {
    localStorage.setItem(KEY, JSON.stringify({ ts: Date.now() - 60_000, payload: snap(AT_1013) }));
    render(<TopNineApp />);
    expect(screen.queryByTestId(/^top-nine-tile-/)).toBeNull();
    expect(screen.getByTestId('top-nine-empty').textContent).toContain('Waiting for the Nova desk');
  });

  it('keeps "Keep on top" locked with its reason outside the desktop app', () => {
    render(<TopNineApp />);
    const btn = screen.getByTestId('top-nine-on-top');
    expect(btn).toHaveProperty('disabled', true);
    expect(btn.getAttribute('data-why')).toContain('desktop app');
  });
});
