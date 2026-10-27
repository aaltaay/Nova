/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DESK_POLL_SNAP_KEY_PREFIX } from '../constantGroups/global_bar';
import { TOP_NINE_LIST_KEY, TOP_NINE_NO_DESK, TOP_NINE_OPEN_WAIT_MS, TOP_NINE_SHARE, TOP_NINE_VIEWER_KEY } from './topNineConstants';
import { TOP_NINE_SCHEMA_VERSION, type TopNineRow, type TopNineSnapshot } from './topNineSnapshot';

const chimeTopNine = vi.fn((_on: boolean) => 'played');
const beepTopNineHalt = vi.fn((_on: boolean) => 'played');
vi.mock('./topNineSound', async (load) => ({
  ...(await load<typeof import('./topNineSound')>()),
  chimeTopNine: (on: boolean) => chimeTopNine(on),
  beepTopNineHalt: (on: boolean) => beepTopNineHalt(on),
}));

const requestOpenOnDesk = vi.fn(async (_symbol: string, _opts: { from?: string; waitMs: number }) => false);
vi.mock('../workspace', () => ({ requestOpenOnDesk: (s: string, o: { from?: string; waitMs: number }) => requestOpenOnDesk(s, o) }));

import TopNineApp from './TopNineApp';

function board(symbols: string[], halted: readonly string[] = ['SMX']): TopNineRow[] {
  return symbols.map((symbol, i) => ({
    symbol, rank: i + 1, changePct: 0.7 - i / 10, price: 2, volume: 5_800_000, float: 81_400, halted: halted.includes(symbol),
  }));
}

function snap(gainers: string[], halted?: readonly string[]): TopNineSnapshot {
  return {
    schema_version: TOP_NINE_SCHEMA_VERSION,
    source: { kind: 'live' },
    asOf: 1_792_160_040,
    lists: {
      gappers: { rows: [], total: 14 },
      gainers: { rows: board(gainers, halted), total: 50 },
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
    chimeTopNine.mockClear();
    beepTopNineHalt.mockClear();
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
    // Change is the Scanner's fraction of the previous close: 0.7 reads +70%, never +0.7%.
    expect(screen.getByTestId('top-nine-tile-XLAB').textContent).toContain('+70.00%');
    expect(screen.getByTestId('top-nine-tile-XLAB').textContent).not.toContain('+0.7%');
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

  it('chimes for a switch on screen, and not for one whose only riser was muted by a right-click', () => {
    render(<TopNineApp />);
    act(() => send(snap(AT_1014)));
    expect(chimeTopNine).toHaveBeenCalledTimes(1);

    // ZTG, SMX and FVNNU rose on that board; mute all three and send the reverse: only WORX rises.
    for (const sym of ['ZTG', 'SMX', 'FVNNU']) {
      fireEvent.contextMenu(screen.getByTestId(`top-nine-tile-${sym}`), { clientX: 100, clientY: 100 });
      expect(screen.getByTestId('top-nine-menu-mute').textContent).toContain(`Mute ${sym}`);
      fireEvent.click(screen.getByTestId('top-nine-menu-mute'));
    }
    expect(screen.queryByTestId('top-nine-menu')).toBeNull();
    expect(screen.getByTestId('top-nine-muted-ZTG')).toBeTruthy();
    act(() => send(snap(AT_1013)));
    expect(chimeTopNine).toHaveBeenCalledTimes(2);
    act(() => send(snap(['XLAB', 'ZTG', 'WORX', 'SMX', 'FVNNU', 'SGRX', 'TCRT', 'SITC', 'CORD'])));
    expect(chimeTopNine).toHaveBeenCalledTimes(2);

    // Unmute from the same menu.
    fireEvent.contextMenu(screen.getByTestId('top-nine-tile-ZTG'), { clientX: 100, clientY: 100 });
    expect(screen.getByTestId('top-nine-menu-mute').textContent).toContain('Unmute ZTG');
    fireEvent.click(screen.getByTestId('top-nine-menu-mute'));
    expect(screen.queryByTestId('top-nine-muted-ZTG')).toBeNull();
  });

  it('beeps when a stock on screen halts, not for one already halted on the first board', () => {
    render(<TopNineApp />);
    expect(beepTopNineHalt).not.toHaveBeenCalled();
    act(() => send(snap(AT_1013, ['SMX', 'XLAB'])));
    expect(beepTopNineHalt).toHaveBeenCalledTimes(1);
    act(() => send(snap(AT_1013, ['SMX', 'XLAB'])));
    expect(beepTopNineHalt).toHaveBeenCalledTimes(1);
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
