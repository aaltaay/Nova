/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetNavRailStoreForTests, setNavPage } from '../workspace/navRailStore';
import { NavPageHost } from './NavPageHost';

vi.mock('./RecordsPage', () => ({
  RecordsPage: () => <div data-testid="records-page" />,
}));
vi.mock('../market_board', () => ({
  MarketPage: () => <div data-testid="market-page-stub" />,
}));
vi.mock('./AccountPage', () => ({
  AccountPage: () => <div data-testid="account-page" />,
}));
vi.mock('../cryptos', () => ({
  CryptosPage: () => <div data-testid="cryptos-page-stub" />,
}));
vi.mock('../bot/BotsGroupPage', () => ({ BotsGroupPage: () => <div data-testid="bots-group-stub" /> }));
vi.mock('../bot/LiveTraderBotsPage', () => ({
  LiveTraderBotsPage: ({ onOpenTrader }: { onOpenTrader?: (s: string) => void }) => (
    <button type="button" data-testid="lt-bots-stub" onClick={() => onOpenTrader?.('XYZ')} />
  ),
}));
vi.mock('../bot/BotsPage', () => ({ BotsPage: () => <div data-testid="strategy-bots-stub" /> }));

describe('NavPageHost', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    resetNavRailStoreForTests();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('shows the dashboard by default and swaps in Records from the store', () => {
    act(() => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeTruthy();
    act(() => {
      setNavPage('records');
    });
    expect(container.querySelector('[data-testid="records-page"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
    act(() => {
      setNavPage('dashboard');
    });
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeTruthy();
  });

  it('routes the Account page (lazy) from the store', async () => {
    await act(async () => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    await act(async () => {
      setNavPage('account');
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="account-page"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
  });

  it("gives LiveTrader Bots, the followed traders' page, the desk's way to open a ticker in the Trader", async () => {
    const opened: string[] = [];
    await act(async () => {
      root.render(
        <NavPageHost onOpenTrader={(s) => opened.push(s)}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    await act(async () => {
      setNavPage('bots-live-trader');
    });
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      (container.querySelector('[data-testid="lt-bots-stub"]') as HTMLElement).click();
    });
    expect(opened).toEqual(['XYZ']);
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
  });

  it('routes the Cryptos page (lazy) from the store', async () => {
    await act(async () => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    await act(async () => {
      setNavPage('cryptos');
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="cryptos-page-stub"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
  });

  it('routes the Bots group: Bots (empty for now), LiveTrader Bots and Strategy Bots (2026-10-15)', async () => {
    await act(async () => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    for (const [page, stub] of [['bots', 'bots-group-stub'], ['bots-live-trader', 'lt-bots-stub'],
      ['bots-strategy', 'strategy-bots-stub']] as const) {
      await act(async () => {
        setNavPage(page);
      });
      await act(async () => {
        await Promise.resolve();
      });
      expect(container.querySelector(`[data-testid="${stub}"]`)).toBeTruthy();
      expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
    }
  });

  it('routes the Market page (lazy) from the store', async () => {
    await act(async () => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    await act(async () => {
      setNavPage('market');
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="market-page-stub"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
  });
});
