/**
 * @vitest-environment jsdom
 *
 * The Cryptos page (ADR 040): the sample desk shows the approved mockup's figures and asks nothing; every number
 * explains itself in a hover card; the live desk states an old backend, a switched-off page and a failed read.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CRYPTOS_OFF, CRYPTOS_OLD_API } from './constants';
import { CryptosPage } from './CryptosPage';
import { CRYPTO_TIP_DELAY_MS } from './tips/TipHost';

const route = vi.hoisted(() => ({ sample: true }));
vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => route.sample }));

const tipText = () => screen.queryByTestId('crypto-tip')?.textContent ?? null;

function hover(el: Element) {
  fireEvent.mouseEnter(el);
  act(() => {
    vi.advanceTimersByTime(CRYPTO_TIP_DELAY_MS + 10);
  });
}

describe('Cryptos page on the sample desk', () => {
  beforeEach(() => {
    route.sample = true;
    vi.useFakeTimers();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('draws the mockup and asks the backend for nothing', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<CryptosPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('crypto-kpi-btc').textContent).toContain('$112,480');
    expect(screen.getByTestId('crypto-kpi-cap').textContent).toContain('$3.94T');
    expect(screen.getByTestId('crypto-kpi-liq').textContent).toContain('No free source yet');
    expect(screen.getAllByTestId(/^crypto-coin-/)).toHaveLength(13);
    expect(screen.getAllByTestId(/^crypto-bridge-[A-Z]+$/)).toHaveLength(8);
    expect(screen.getByTestId('crypto-chart')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reads the bridge as ahead, behind or unknown -- never a guess', () => {
    render(<CryptosPage onOpenTrader={() => {}} />);
    const mara = screen.getByTestId('crypto-bridge-MARA');
    expect(mara.textContent).toContain('▲ ahead +2.7');
    const clsk = screen.getByTestId('crypto-bridge-CLSK');
    expect(clsk.textContent).toContain('No print yet');
    expect(clsk.textContent).toContain('unknown');
  });

  it('explains a number on hover and on focus, and closes on Escape', () => {
    render(<CryptosPage onOpenTrader={() => {}} />);
    hover(screen.getByTestId('crypto-kpi-fng'));
    expect(tipText()).toContain('Fear & Greed index');
    expect(tipText()).toContain('A week ago: 54');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(tipText()).toBeNull();

    const read = within(screen.getByTestId('crypto-bridge-MARA')).getByText(/ahead/).parentElement!;
    hover(read);
    expect(tipText()).toContain('ahead by 2.7 points');

    fireEvent.focus(screen.getByTestId('crypto-kpi-liq'));
    act(() => {
      vi.advanceTimersByTime(CRYPTO_TIP_DELAY_MS + 10);
    });
    expect(tipText()).toContain('Liquidations');
    expect(tipText()).toContain('Not known on this desk');
  });

  it('opens a stock or an ETF in the Trader, and charts a clicked coin', () => {
    const onOpenTrader = vi.fn();
    render(<CryptosPage onOpenTrader={onOpenTrader} />);
    fireEvent.click(within(screen.getByTestId('crypto-bridge-MARA')).getByRole('button'));
    expect(onOpenTrader).toHaveBeenCalledWith('MARA');
    fireEvent.click(within(screen.getByTestId('crypto-coin-BTC')).getByText('IBIT'));
    expect(onOpenTrader).toHaveBeenCalledWith('IBIT');
    expect(screen.getByTestId('crypto-chart-card').textContent).toContain('BTC · Bitcoin');
    fireEvent.click(screen.getByTestId('crypto-coin-ETH'));
    expect(screen.getByTestId('crypto-chart-card').textContent).toContain('ETH · Ether');
  });

  it('filters the coins by group and sorts the movers first', () => {
    render(<CryptosPage onOpenTrader={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Memes' }));
    expect(screen.getAllByTestId(/^crypto-coin-/).map((r) => r.dataset.testid)).toEqual(['crypto-coin-DOGE', 'crypto-coin-PEPE']);
    expect(screen.queryByTestId('crypto-coin-BTC')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /^All/ }));
    fireEvent.click(screen.getByRole('tab', { name: 'Movers 24h' }));
    const rows = screen.getAllByTestId(/^crypto-coin-/);
    expect(rows).toHaveLength(13);
    expect(rows.slice(0, 4).map((r) => r.dataset.testid)).toEqual(['crypto-coin-PEPE', 'crypto-coin-DOGE', 'crypto-coin-SOL', 'crypto-coin-SUI']);
  });
});

describe('Cryptos page on the live desk', () => {
  beforeEach(() => {
    route.sample = false;
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('says so when the backend is older than the page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Not Found', { status: 404 })));
    render(<CryptosPage onOpenTrader={() => {}} />);
    expect(await screen.findByText(CRYPTOS_OLD_API)).toBeTruthy();
  });

  it('says so when the page is switched off', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ schema_version: 1, enabled: false }), { status: 200 })));
    render(<CryptosPage onOpenTrader={() => {}} />);
    expect(await screen.findByText(CRYPTOS_OFF)).toBeTruthy();
  });

  it('names a failed read instead of drawing nothing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 502 })));
    render(<CryptosPage onOpenTrader={() => {}} />);
    expect(await screen.findByText(/The crypto board did not load: HTTP 502/)).toBeTruthy();
  });
});
