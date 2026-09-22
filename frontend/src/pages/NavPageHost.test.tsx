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
vi.mock('./DeskPage', () => ({
  DeskPage: () => <div data-testid="desk-page" />,
}));
vi.mock('./AccountPage', () => ({
  AccountPage: () => <div data-testid="account-page" />,
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

  it('shows the dashboard by default and swaps in Desk / Records from the store', () => {
    act(() => {
      root.render(
        <NavPageHost onOpenTrader={() => {}}>
          <div data-testid="dashboard-stub" />
        </NavPageHost>,
      );
    });
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeTruthy();
    act(() => {
      setNavPage('desk');
    });
    expect(container.querySelector('[data-testid="desk-page"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="dashboard-stub"]')).toBeNull();
    act(() => {
      setNavPage('records');
    });
    expect(container.querySelector('[data-testid="records-page"]')).toBeTruthy();
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
});
