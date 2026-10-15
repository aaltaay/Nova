/**
 * @vitest-environment jsdom
 */
import { act, type ReactNode } from 'react';
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
vi.mock('../followed_traders', () => ({
  FollowedTradersPage: ({ top }: { top?: ReactNode }) => <div data-testid="followed-page-stub">{top}</div>,
}));
vi.mock('../bot/BotLiveTradersCard', () => ({
  BotLiveTradersCard: () => <section data-testid="live-traders-stub" />,
}));

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

  it('routes the Followed traders page (lazy) from the store', async () => {
    await act(async () => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    await act(async () => {
      setNavPage('followed');
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="followed-page-stub"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
    // The Live Trader bots' panel rides at its top (ADR 044 amendment, 2026-10-15); it loads on its own.
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="followed-page-stub"] [data-testid="live-traders-stub"]')).toBeTruthy();
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
