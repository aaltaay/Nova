/**
 * @vitest-environment jsdom
 *
 * The Market page (ADR 053): the sample desk shows the approved mockup's figures and asks nothing; the live desk
 * asks for each block's switch, remembers the switches, and states an old backend, a switched-off page and a
 * failed read.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MARKET_OFF, MARKET_OLD_API, MARKET_PERIODS_STORAGE_KEY } from './constants';
import { MarketPage } from './MarketPage';
import { DEFAULT_PERIODS, parsePeriods } from './periods';
import { sampleMarketBoard } from './sampleMarket';
import { resetKeptBoardsForTests } from './useMarketBoard';

const route = vi.hoisted(() => ({ sample: true }));
vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => route.sample }));
vi.mock('../workspace', () => ({ setNavPage: vi.fn() }));

function respond(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });
}

describe('Market page on the sample desk', () => {
  beforeEach(() => {
    route.sample = true;
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('draws the mockup and asks the backend for nothing', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<MarketPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('market-day-read').textContent).toContain('BULLISH');
    expect(screen.getByTestId('market-day-read').textContent).toContain('5 of 6 checks green');
    expect(screen.getAllByTestId(/^market-tile-/)).toHaveLength(10);
    expect(screen.getByTestId('market-tile-es').textContent).toContain('6,842.50');
    expect(within(screen.getByTestId('market-sectors')).getAllByText(/^XL/).length).toBeGreaterThanOrEqual(11);
    expect(screen.getByTestId('market-climate').textContent).toContain('Theme of the day');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('switches a block on its own and never writes storage', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    render(<MarketPage onOpenTrader={() => {}} />);
    const climate = screen.getByTestId('market-climate');
    fireEvent.click(within(climate).getByRole('radio', { name: '7 D' }));
    expect(screen.getByTestId('market-climate').textContent).toContain('Theme of the week');
    expect(within(screen.getByTestId('market-sectors')).getByRole('radio', { name: '1 D' }).getAttribute('aria-checked')).toBe('true');
    expect(setItem).not.toHaveBeenCalledWith(MARKET_PERIODS_STORAGE_KEY, expect.anything());
    setItem.mockRestore();
  });

  it('opens a leader in the Trader', () => {
    const open = vi.fn();
    render(<MarketPage onOpenTrader={open} />);
    fireEvent.click(within(screen.getByTestId('market-sectors')).getByRole('button', { name: 'NVDA' }));
    expect(open).toHaveBeenCalledWith('NVDA');
  });
});

describe('Market page on the live desk', () => {
  beforeEach(() => {
    route.sample = false;
    window.localStorage.clear();
    resetKeptBoardsForTests();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('asks for every block’s switch, and remembers a change', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(url);
      const q = new URL(url, 'http://desk').searchParams;
      return respond(sampleMarketBoard(parsePeriods({
        schema_version: 1, sectors: q.get('sectors'), industries: q.get('industries'), climate: q.get('climate'),
        top: { kind: q.get('top'), period: q.get('top_period') },
      })));
    }));
    render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    expect(urls[0]).toContain('/api/market/board?sectors=1D&industries=1D&climate=1D&top=movers&top_period=1D');
    fireEvent.click(within(screen.getByTestId('market-industries')).getByRole('radio', { name: '7 D' }));
    await act(async () => {});
    expect(urls[urls.length - 1]).toContain('industries=7D');
    const saved = JSON.parse(window.localStorage.getItem(MARKET_PERIODS_STORAGE_KEY) ?? '{}');
    expect(parsePeriods(saved)).toEqual({ ...DEFAULT_PERIODS, industries: '7D' });
  });

  it('opens on the remembered switches', async () => {
    window.localStorage.setItem(MARKET_PERIODS_STORAGE_KEY, JSON.stringify({
      schema_version: 1, sectors: '30D', industries: '1D', climate: '7D', top: { kind: 'biggest', period: '7D' },
    }));
    const fetchMock = vi.fn(() => respond(sampleMarketBoard(DEFAULT_PERIODS)));
    vi.stubGlobal('fetch', fetchMock);
    render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('sectors=30D&industries=1D&climate=7D&top=biggest&top_period=7D');
  });

  it('states an old backend and a switched-off page', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond({}, 404)));
    render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    expect(screen.getByTestId('market-page').textContent).toContain(MARKET_OLD_API);
    cleanup();
    vi.stubGlobal('fetch', vi.fn(() => respond({ ...sampleMarketBoard(DEFAULT_PERIODS), enabled: false })));
    render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    expect(screen.getByTestId('market-page').textContent).toContain(MARKET_OFF);
  });

  it('says when an answer cannot be read, never drawing a guess', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond({ schema_version: 2 })));
    render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    expect(screen.getByTestId('market-page').textContent).toContain('not one this desk can read');
  });
});

describe('Market page: every symbol opens the Trader (ADR 053 amendment 2026-10-13 evening)', () => {
  beforeEach(() => {
    route.sample = true;
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it('opens a sector ETF and an industry ETF', () => {
    const open = vi.fn();
    render(<MarketPage onOpenTrader={open} />);
    fireEvent.click(within(screen.getByTestId('market-sectors')).getByRole('button', { name: 'XLK' }));
    fireEvent.click(within(screen.getByTestId('market-industries')).getByRole('button', { name: 'XOP' }));
    expect(open.mock.calls).toEqual([['XLK'], ['XOP']]);
  });

  it('opens a row’s ETF on a click anywhere on it, and only the leader on the leader', () => {
    const open = vi.fn();
    render(<MarketPage onOpenTrader={open} />);
    fireEvent.click(screen.getByTestId('market-row-XLV'));
    expect(open).toHaveBeenLastCalledWith('XLV');
    open.mockClear();
    fireEvent.click(within(screen.getByTestId('market-row-XLK')).getByRole('button', { name: 'NVDA' }));
    expect(open.mock.calls).toEqual([['NVDA']]);
  });

  it('gives every sector a top-stocks card, each stock and ETF a way into the Trader', () => {
    const open = vi.fn();
    render(<MarketPage onOpenTrader={open} />);
    const top = screen.getByTestId('market-top');
    expect(top.querySelectorAll('.mk-top__card')).toHaveLength(11);
    const health = screen.getByTestId('market-top-card-XLV');
    expect(health.querySelectorAll('.mk-top__row').length).toBeGreaterThan(0);
    fireEvent.click(within(health).getByRole('button', { name: 'XLV' }));
    fireEvent.click(health.querySelector('.mk-top__row') as Element);
    fireEvent.click(within(screen.getByTestId('market-top-card-XLU')).getByRole('button', { name: 'VST' }));
    expect(open.mock.calls).toEqual([['XLV'], ['LLY'], ['VST']]);
  });

  it('opens a top runner from the climate card', () => {
    const open = vi.fn();
    render(<MarketPage onOpenTrader={open} />);
    fireEvent.click(within(screen.getByTestId('market-climate')).getByRole('button', { name: 'RUNR' }));
    expect(open).toHaveBeenCalledWith('RUNR');
  });

  it('draws the runners chart across the climate card, with its unrecorded sessions hatched', () => {
    render(<MarketPage onOpenTrader={() => {}} />);
    const chart = within(screen.getByTestId('market-climate')).getByTestId('market-runners');
    expect(chart.querySelectorAll('rect.mk-runners__none')).toHaveLength(2);
    fireEvent.click(within(chart).getByRole('button', { name: 'Open the runners chart large' }));
    expect(screen.getByTestId('market-runners-large').textContent).toContain('21 sessions, 19 recorded');
  });

  it('shows plain text, not a dead button, where nothing can open the Trader', () => {
    render(<MarketPage />);
    expect(within(screen.getByTestId('market-sectors')).queryByRole('button', { name: 'XLK' })).toBeNull();
    expect(within(screen.getByTestId('market-sectors')).getByText('XLK')).toBeTruthy();
  });
});

describe('Market page: closing and opening again', () => {
  beforeEach(() => {
    route.sample = false;
    window.localStorage.clear();
    resetKeptBoardsForTests();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('opens again on the last board at once, never "Reading the market"', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond(sampleMarketBoard(DEFAULT_PERIODS))));
    const first = render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    expect(screen.getByTestId('market-day-read')).toBeTruthy();
    first.unmount();

    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));    // the backend has not answered yet
    render(<MarketPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('market-page').textContent).not.toContain('Reading the market');
    expect(screen.getByTestId('market-day-read').textContent).toContain('BULLISH');
    expect(screen.getAllByTestId(/^market-tile-/)).toHaveLength(10);
  });

  it('dims a future in CME’s daily pause and says when it last traded', async () => {
    const board = sampleMarketBoard(DEFAULT_PERIODS);
    const es = board.quotes[0];
    const stale = { ...es, stale: true, data_type: 'bars' as const, price_basis: 'bars' as const, at: es.at };
    vi.stubGlobal('fetch', vi.fn(() => respond({ ...board, quotes: [stale, ...board.quotes.slice(1)] })));
    render(<MarketPage onOpenTrader={() => {}} />);
    await act(async () => {});
    const tile = screen.getByTestId('market-tile-es');
    expect(tile.className).toContain('is-stale');
    expect(tile.textContent).toContain('6,842.50');
    expect(tile.textContent).toContain('as of 09:52');
  });
});
