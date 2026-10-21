/**
 * @vitest-environment jsdom
 *
 * The Forex page (ADR 062): the sample desk shows the approved mockup v2's day and asks nothing; the whole market's
 * size leads (the BIS survey's, labelled), every currency carries its own size and is listed biggest first, a currency
 * IBKR does not price says so, the real moves by its future, a currency whose futures and strength disagree is
 * flagged, the card says everything about one currency, and the live desk asks for the chosen period, remembers the
 * switches and states an old backend, a switched-off page, the weekend and what the reads wait for.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usd } from '../world_board/format';
import { project } from '../world_board/project';
import { WORLD_VIEW } from '../world_board/worldLand';
import { FOREX_OFF, FOREX_OLD_API, FOREX_PREFS_STORAGE_KEY } from './constants';
import { cross, strengths } from './cross';
import { rateWord } from './CurrencyTip';
import { sunRows } from './FollowTheSun';
import { ForexPage } from './ForexPage';
import { majorOrder } from './MajorPairs';
import { DEFAULT_PREFS, parsePrefs } from './prefs';
import { sampleForexBoard } from './sampleForex';
import type { ForexBoard } from './types';
import { resetKeptForexBoardsForTests } from './useForexBoard';

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

describe('Forex page on the sample desk', () => {
  beforeEach(() => {
    route.sample = true;
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('draws the mockup day, the whole market first, and asks the backend for nothing', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<ForexPage />);
    const all = screen.getByTestId('forex-all');
    expect(all.textContent).toContain('$9.51T');
    expect(all.textContent).toContain('BIS survey · Apr 2025 average');
    expect(all.textContent).toContain('UK 38%');
    expect(screen.getByTestId('forex-read').textContent).toContain('Safe havens bought');
    expect(screen.getAllByTestId(/^forex-row-/)).toHaveLength(19);
    expect(screen.getAllByTestId(/^forex-bubble-/)).toHaveLength(19);
    expect(screen.getByTestId('forex-sun')).toBeTruthy();
    expect(screen.getByTestId('forex-pairs')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('lists every currency biggest first, each with its own size', () => {
    render(<ForexPage />);
    const ids = screen.getAllByTestId(/^forex-row-/).map((r) => r.getAttribute('data-testid'));
    expect(ids.slice(0, 3)).toEqual(['forex-row-USD', 'forex-row-EUR', 'forex-row-JPY']);
    expect(ids[ids.length - 1]).toBe('forex-row-ZAR');
    const eur = screen.getByTestId('forex-row-EUR').textContent ?? '';
    expect(eur).toContain('$2.71T');
    expect(eur).toContain('29% of trades');
    expect(screen.getByTestId('forex-bubble-USD').textContent).toContain('USD $8.47T');
  });

  it('says so when IBKR has no price, and moves the real by its future', () => {
    render(<ForexPage />);
    const inr = screen.getByTestId('forex-row-INR');
    expect(inr.textContent).toContain('no IBKR price');
    expect(inr.textContent).toContain('no price');
    expect(screen.getByTestId('forex-bubble-INR').getAttribute('class')).toContain('is-none');
    expect(screen.getByTestId('forex-row-BRL').textContent).toContain('from futures');
  });

  it('flags a currency whose futures buyers were eager while it fell, or the reverse', () => {
    render(<ForexPage />);
    expect(screen.getByTestId('forex-row-MXN').textContent).toContain('≠');
    expect(screen.getByTestId('forex-row-CHF').textContent).toContain('≠');
    expect(screen.getByTestId('forex-row-EUR').textContent).not.toContain('≠');
  });

  it('names what rose and fell most in each session, with its desks’ share', () => {
    render(<ForexPage />);
    const asia = screen.getByTestId('forex-session-asia').textContent ?? '';
    expect(asia).toContain('JPY');
    expect(asia).toContain('desks in Asia: 28% of all forex');
    expect(screen.getByTestId('forex-session-new_york').textContent).toContain('now');
    expect(screen.getByTestId('forex-usd').textContent).toContain('in 89% of all trades · $8.47T a day');
  });

  it('says everything about one currency on its card', () => {
    render(<ForexPage />);
    fireEvent.mouseEnter(screen.getByTestId('forex-bubble-JPY'));
    const tip = screen.getByTestId('forex-tip-JPY').textContent ?? '';
    expect(screen.getByTestId('forex-tip-size-JPY').textContent).toContain('$1.61T · 17% of all trades · #3');
    expect(tip).toContain('USD/JPY · $1.37T a day');
    expect(tip).toContain('(the yen up)');
    expect(tip).toContain('Strength by session: Asia');
    expect(tip).toContain('published every three years, not live');
    expect(tip).toContain('the public part of forex');
  });

  it('keeps the definitions behind "How to read"', () => {
    render(<ForexPage />);
    expect(screen.queryByTestId('forex-defs')).toBeNull();
    const button = screen.getByTestId('forex-how-to-read');
    fireEvent.click(button);
    const defs = screen.getByTestId('forex-defs').textContent ?? '';
    expect(defs).toContain('A day:');
    expect(defs).toContain('Strength:');
    expect(defs).toContain('Futures:');
  });

  it('switches what the map shows and the period, and never writes storage', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    render(<ForexPage />);
    fireEvent.click(screen.getByTestId('forex-color-by-futures'));
    expect(screen.getByTestId('forex-color-by-futures').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('forex-page').textContent).toContain('Futures bought');
    expect(screen.getByTestId('forex-bubble-INR').textContent).toContain('no futures');
    fireEvent.click(screen.getByTestId('forex-period-30D'));
    expect(screen.getByTestId('forex-period-30D').getAttribute('aria-pressed')).toBe('true');
    expect(setItem).not.toHaveBeenCalledWith(FOREX_PREFS_STORAGE_KEY, expect.anything());
    setItem.mockRestore();
  });

  it('draws the majors strongest first: the yen against the Aussie is up', () => {
    render(<ForexPage />);
    const cell = screen.getByTestId('forex-pair-JPYAUD');
    expect(within(cell).getByText(/^\+/)).toBeTruthy();
    expect(cell.querySelector('rect')?.getAttribute('class')).toContain('is-up');
  });
});

describe('Forex page on the live desk', () => {
  beforeEach(() => {
    route.sample = false;
    window.localStorage.clear();
    resetKeptForexBoardsForTests();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('asks for the chosen period and remembers it', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(url);
      return respond(sampleForexBoard(url.includes('7D') ? '7D' : '1D'));
    }));
    render(<ForexPage />);
    await flush();
    expect(urls[0]).toContain('/api/forex/board?period=1D');
    fireEvent.click(screen.getByTestId('forex-period-7D'));
    await flush();
    expect(urls.some((u) => u.includes('period=7D'))).toBe(true);
    expect(parsePrefs(JSON.parse(window.localStorage.getItem(FOREX_PREFS_STORAGE_KEY) ?? 'null')).period).toBe('7D');
  });

  it('keeps the last board labelled by its own period while another period loads', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => (url.includes('7D') ? new Promise(() => {}) : respond(sampleForexBoard('1D')))));
    render(<ForexPage />);
    await flush();
    fireEvent.click(screen.getByTestId('forex-period-7D'));
    await flush();
    expect(screen.getByTestId('forex-period-loading').textContent).toContain('Loading 7D');
    expect(screen.getByTestId('forex-page').textContent).toContain('biggest first · 1D');
  });

  it('says what the reads wait for on one line, and that the market is shut for the weekend', async () => {
    const board: ForexBoard = {
      ...sampleForexBoard(), loading: true, budget: { history_left: 24, history_headroom: 30, waiting: 'history' },
      fx_day: { ...sampleForexBoard().fx_day, open: false, next_open_at: sampleForexBoard().generated_at + 3600 },
    };
    vi.stubGlobal('fetch', vi.fn(() => respond(board)));
    render(<ForexPage />);
    await flush();
    const status = screen.getByTestId('forex-status');
    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(status.textContent).toContain('Reading each currency from IBKR');
    expect(status.textContent).toContain('24 requests left this 10 minutes, Forex reads above 30');
    expect(status.textContent).toContain('closed for the weekend');
  });

  it('says so when the backend has no Forex page yet, and when the page is off', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond({}, 404)));
    render(<ForexPage />);
    await flush();
    expect(screen.getByTestId('forex-page').textContent).toContain(FOREX_OLD_API);
    cleanup();
    resetKeptForexBoardsForTests();
    vi.stubGlobal('fetch', vi.fn(() => respond({ ...sampleForexBoard(), enabled: false })));
    render(<ForexPage />);
    await flush();
    expect(screen.getByTestId('forex-page').textContent).toContain(FOREX_OFF);
  });

  it('shows a refused future with IBKR’s own words and no invented number', async () => {
    const board = sampleForexBoard();
    const eur = board.currencies.find((c) => c.code === 'EUR')!;
    Object.assign(eur.futures, {
      basis: null, instrument: null, traded_usd: null, up_usd: null, down_usd: null, pressure_usd: null,
      pressure_pct: null, error: 'waiting for IBKR',
      refused: [{ instrument: 'Euro FX futures (6E)', error: '10089: Requested market data requires additional subscription. More' }],
    });
    vi.stubGlobal('fetch', vi.fn(() => respond(board)));
    render(<ForexPage />);
    await flush();
    const row = screen.getByTestId('forex-row-EUR');
    expect(row.textContent).toContain('no feed');
    fireEvent.mouseEnter(screen.getByTestId('forex-bubble-EUR'));
    expect(screen.getByTestId('forex-tip-EUR').textContent).toContain('10089: Requested market data requires additional subscription.');
  });
});

describe('Forex page pieces', () => {
  it('works a pair out from its two dollar moves, as the backend does', () => {
    expect(cross(1, -1)).toBeCloseTo((1.01 / 0.99 - 1) * 100, 10);
    const s = strengths({ USD: 0, EUR: 1, JPY: -1 });
    expect(s.EUR).toBeCloseTo((1 + (1.01 / 0.99 - 1) * 100) / 2, 10);
    expect(Object.keys(strengths({ USD: 0 }))).toHaveLength(0);
  });

  it('falls back to the defaults for another prefs version or an unknown value', () => {
    expect(parsePrefs({ schema_version: 9, period: '7D', color_by: 'futures' })).toEqual(DEFAULT_PREFS);
    expect(parsePrefs({ schema_version: 1, period: '30D', color_by: 'futures' })).toEqual({ period: '30D', colorBy: 'futures' });
    expect(parsePrefs({ schema_version: 1, period: '2D', color_by: 'move' })).toEqual(DEFAULT_PREFS);
  });

  it('words a sum that rounds up to 1,000 of its unit in the next one', () => {
    expect(usd(-999.6e6, true)).toBe('−$1.0B');
    expect(usd(999.7e9)).toBe('$1.00T');
    expect(usd(999_960)).toBe('$1.0M');
    expect(usd(999.6)).toBe('$1.0K');
    expect(usd(-998e6, true)).toBe('−$998M');
    expect(usd(9.51024e12)).toBe('$9.51T');
  });

  it('words a rate as the market quotes it', () => {
    expect(rateWord(150.4213)).toBe('150.42');
    expect(rateWord(18.5312)).toBe('18.531');
    expect(rateWord(1.16381)).toBe('1.1638');
    expect(rateWord(null)).toBe('--');
  });

  it('places every currency inside the map', () => {
    for (const c of sampleForexBoard().currencies) {
      const [x, y] = project(c.lon, c.lat);
      expect(x).toBeGreaterThan(0);
      expect(x).toBeLessThan(WORLD_VIEW.width);
      expect(y).toBeGreaterThan(0);
      expect(y).toBeLessThan(WORLD_VIEW.height);
    }
  });

  it('orders Follow the sun and the majors strongest first', () => {
    const board = sampleForexBoard();
    expect(sunRows(board.sun, 'strength')[0]).toBe('JPY');
    expect(sunRows(board.sun, 'futures')[0]).toBe('USD');
    expect(majorOrder(board.currencies).map((c) => c.code)[0]).toBe('JPY');
    expect(majorOrder(board.currencies)).toHaveLength(8);
  });
});
