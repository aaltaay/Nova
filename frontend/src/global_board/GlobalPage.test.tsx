/**
 * @vitest-environment jsdom
 *
 * The Global page (ADR 060): the sample desk shows the approved mockup's day and asks nothing; the live desk asks for
 * the chosen period, remembers the switches, ranks markets by pressure, names a row that reads its ETF and opens that
 * ETF in the Trader, flags a market whose pressure and index move disagree, and states an old backend, a switched-off
 * page and a refused feed.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GLOBAL_OFF, GLOBAL_OLD_API, GLOBAL_PREFS_STORAGE_KEY } from './constants';
import { ranked } from './ExchangeList';
import { usd } from './format';
import { GlobalPage } from './GlobalPage';
import { DEFAULT_PREFS, parsePrefs } from './prefs';
import { project } from './project';
import { sampleGlobalBoard } from './sampleGlobal';
import type { GlobalBoard } from './types';
import { resetKeptGlobalBoardsForTests } from './useGlobalBoard';
import { WORLD_VIEW } from './worldLand';

const route = vi.hoisted(() => ({ sample: true }));
vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => route.sample }));

function respond(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('Global page on the sample desk', () => {
  beforeEach(() => {
    route.sample = true;
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('draws the mockup day and asks the backend for nothing', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<GlobalPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('global-read').textContent).toContain('Rotation, not an exit');
    expect(screen.getAllByTestId(/^global-row-/)).toHaveLength(16);
    expect(screen.getAllByTestId(/^global-bubble-/)).toHaveLength(16);
    expect(screen.getByTestId('global-sun')).toBeTruthy();
    expect(screen.getByTestId('global-agree')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('ranks the markets by pressure, buyers first', () => {
    render(<GlobalPage />);
    const ids = screen.getAllByTestId(/^global-row-/).map((r) => r.getAttribute('data-testid'));
    expect(ids[0]).toBe('global-row-us');
    expect(ids[ids.length - 1]).toBe('global-row-hk');
  });

  it('flags a market whose buyers were eager while its index fell', () => {
    render(<GlobalPage />);
    expect(screen.getByTestId('global-row-kr').textContent).toContain('≠');
    expect(screen.getByTestId('global-row-us').textContent).not.toContain('≠');
  });

  it('names a row that reads its US-listed ETF and opens that ETF in the Trader', () => {
    const open = vi.fn();
    render(<GlobalPage onOpenTrader={open} />);
    const row = screen.getByTestId('global-row-br');
    expect(row.textContent).toContain('via EWZ');
    fireEvent.click(within(row).getByRole('button', { name: 'EWZ' }));
    expect(open).toHaveBeenCalledWith('EWZ');
  });

  it('shows a market card on hover, with where its money and move came from', () => {
    render(<GlobalPage />);
    fireEvent.mouseEnter(screen.getByTestId('global-bubble-jp'));
    const tip = screen.getByTestId('global-tip-jp');
    expect(tip.textContent).toContain('Nikkei 225 futures');
    expect(tip.textContent).toContain('JPY');
  });

  it('switches the period and the colour and never writes storage', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    render(<GlobalPage />);
    fireEvent.click(screen.getByTestId('global-period-30D'));
    expect(screen.getByTestId('global-period-30D').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('global-color-by-move'));
    expect(screen.getByTestId('global-color-by-move').getAttribute('aria-pressed')).toBe('true');
    expect(setItem).not.toHaveBeenCalledWith(GLOBAL_PREFS_STORAGE_KEY, expect.anything());
    setItem.mockRestore();
  });
});

describe('Global page on the live desk', () => {
  beforeEach(() => {
    route.sample = false;
    window.localStorage.clear();
    resetKeptGlobalBoardsForTests();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('asks for the chosen period and remembers it', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(url);
      return respond(sampleGlobalBoard(url.includes('7D') ? '7D' : '1D'));
    }));
    render(<GlobalPage />);
    await flush();
    expect(urls[0]).toContain('/api/global/board?period=1D');
    fireEvent.click(screen.getByTestId('global-period-7D'));
    await flush();
    expect(urls.some((u) => u.includes('period=7D'))).toBe(true);
    expect(parsePrefs(JSON.parse(window.localStorage.getItem(GLOBAL_PREFS_STORAGE_KEY) ?? 'null')).period).toBe('7D');
  });

  it('says so when the backend has no Global page yet', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond({}, 404)));
    render(<GlobalPage />);
    await flush();
    expect(screen.getByTestId('global-page').textContent).toContain(GLOBAL_OLD_API);
  });

  it('says so when the page is turned off', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond({ ...sampleGlobalBoard(), enabled: false })));
    render(<GlobalPage />);
    await flush();
    expect(screen.getByTestId('global-page').textContent).toContain(GLOBAL_OFF);
  });

  it('shows a refused feed with IBKR’s own words and no invented number', async () => {
    const board: GlobalBoard = sampleGlobalBoard();
    const de = board.markets.find((m) => m.id === 'de')!;
    Object.assign(de.flow, {
      basis: null, instrument: null, up_usd: null, down_usd: null, flat_usd: null, traded_usd: null,
      pressure_usd: null, pressure_pct: null, error: 'IBKR refused every instrument of this market',
      refused: [{ instrument: 'DAX futures', error: '10089: Requested market data requires additional subscription' }],
    });
    vi.stubGlobal('fetch', vi.fn(() => respond(board)));
    render(<GlobalPage />);
    await flush();
    const row = screen.getByTestId('global-row-de');
    expect(row.textContent).toContain('no feed');
    expect(row.textContent).toContain('--');
    fireEvent.mouseEnter(screen.getByTestId('global-bubble-de'));
    expect(screen.getByTestId('global-tip-de').textContent).toContain('10089');
  });
});

describe('Global page pieces', () => {
  it('words dollars by their size, signed when asked', () => {
    expect(usd(4.6e9, true)).toBe('+$4.6B');
    expect(usd(-8.7e8, true)).toBe('−$870M');
    expect(usd(1.21e11)).toBe('$121B');
    expect(usd(null)).toBe('--');
  });

  it('falls back to the defaults for another prefs version', () => {
    expect(parsePrefs({ schema_version: 9, period: '7D', color_by: 'move' })).toEqual(DEFAULT_PREFS);
    expect(parsePrefs({ schema_version: 1, period: '30D', color_by: 'move' })).toEqual({ period: '30D', colorBy: 'move' });
  });

  it('places each market inside the map', () => {
    for (const m of sampleGlobalBoard().markets) {
      const [x, y] = project(m.lon, m.lat);
      expect(x).toBeGreaterThan(0);
      expect(x).toBeLessThan(WORLD_VIEW.width);
      expect(y).toBeGreaterThan(0);
      expect(y).toBeLessThan(WORLD_VIEW.height);
    }
    const [tokyoX] = project(139.77, 35.68);
    const [nyX] = project(-74.01, 40.71);
    expect(tokyoX).toBeGreaterThan(nyX);
  });

  it('puts markets with no pressure yet last', () => {
    const board = sampleGlobalBoard();
    const za = board.markets.find((m) => m.id === 'za')!;
    za.flow.pressure_usd = null;
    za.flow.pressure_pct = null;
    expect(ranked(board.markets).at(-1)!.id).toBe('za');
  });
});
