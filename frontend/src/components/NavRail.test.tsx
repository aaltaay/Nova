/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NAV_RAIL_SCHEMA_VERSION, NAV_RAIL_STORAGE_KEY } from '../constantGroups/nav_rail';
import { TRADER_DEFAULT_SYMBOL } from '../constants';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import {
  consumeScannerTabRequest,
  getNavPage,
  publishScannerNavState,
  resetNavRailStoreForTests,
  setNavPage,
} from '../workspace/navRailStore';
import { listScannerNavGroups } from '../workspace/registry';
import { NavRail } from './NavRail';

const { workspace, status, visibility } = vi.hoisted(() => ({
  workspace: { current: { selectedSymbol: 'AAPL' as string | null } },
  status: { current: {} as IbkrClientStatus },
  visibility: { current: {} as Record<string, boolean> },
}));

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace.current,
}));
vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => status.current,
}));
vi.mock('../workspace/useModuleVisibility', () => ({
  useModuleVisibility: () => ({ visibility: visibility.current, setVisible: () => {} }),
}));

function baseStatus(overrides: Partial<IbkrClientStatus> = {}): IbkrClientStatus {
  return {
    enabled: true,
    connected: true,
    transport_connected: true,
    session_reason: 'ok',
    mode: 'live',
    orders_enabled: false,
    short_enabled: false,
    spend_status: 'locked',
    trading_allowed: false,
    trading_allowed_reason: null,
    market_data_type: 1,
    market_data_delayed: false,
    clientReady: true,
    stale: false,
    staleSince: null,
    ...overrides,
  };
}

const onOpenTrader = vi.fn();
const onLeaveTrader = vi.fn();
const toggleSettings = vi.fn();

describe('NavRail', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    resetNavRailStoreForTests();
    consumeScannerTabRequest();
    onOpenTrader.mockReset();
    onLeaveTrader.mockReset();
    toggleSettings.mockReset();
    workspace.current = { selectedSymbol: 'AAPL' };
    status.current = baseStatus();
    visibility.current = {};
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

  function render(props: Partial<Parameters<typeof NavRail>[0]> = {}) {
    act(() => {
      root.render(
        <NavRail
          traderActive={false}
          onOpenTrader={onOpenTrader}
          onLeaveTrader={onLeaveTrader}
          settings={{ open: false, toggle: toggleSettings }}
          {...props}
        />,
      );
    });
  }

  const q = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const click = (id: string) => {
    act(() => {
      (q(id) as HTMLButtonElement).click();
    });
  };
  const testIds = (scope: Element) =>
    Array.from(scope.querySelectorAll('[data-testid]')).map((el) => el.getAttribute('data-testid'));

  it('lists Desk, Trader, Scanner, Account, Bots, Records top to bottom and pins Settings + collapse at the foot', () => {
    render();
    const rail = q('nav-rail')!;
    expect(rail.tagName).toBe('NAV');
    expect(rail.getAttribute('aria-label')).toBe('Navigation');
    const top = testIds(rail.querySelector('.nav-rail__list')!).filter((id) =>
      ['nav-rail-desk', 'nav-rail-trader', 'nav-rail-scanner', 'nav-rail-account', 'nav-rail-bots', 'nav-rail-records'].includes(id!),
    );
    expect(top).toEqual([
      'nav-rail-desk',
      'nav-rail-trader',
      'nav-rail-scanner',
      'nav-rail-account',
      'nav-rail-bots',
      'nav-rail-records',
    ]);
    const foot = rail.querySelector('.nav-rail__foot')!;
    expect(testIds(foot)).toEqual(['nav-rail-settings', 'nav-rail-collapse']);
    expect(q('nav-rail-settings')!.textContent).toMatch(/Settings/);
  });

  it('builds the Scanner tree from the registry groups, in registry order, with group labels', () => {
    render();
    const groups = listScannerNavGroups();
    expect(groups.map((g) => g.group)).toEqual(['lists', 'signals', 'mine']);
    expect(groups[0].modules.map((m) => m.id)).toEqual([
      'gappers', 'gainers', 'losers', 'running_up', 'afterhours', 'large_cap',
    ]);
    expect(groups[1].modules.map((m) => m.id)).toEqual([
      'volume_boost', 'hod_momo', 'catalysts', 'earnings', 'nova_news',
    ]);
    expect(groups[2].modules.map((m) => m.id)).toEqual(['watchlist']);
    const tree = q('nav-rail-scanner-tree')!;
    const labels = Array.from(tree.querySelectorAll('.nav-rail__grp')).map((el) => el.textContent);
    expect(labels).toEqual(['Lists', 'Signals', 'Mine']);
    const children = Array.from(tree.querySelectorAll('[data-tab]')).map((el) => el.getAttribute('data-tab'));
    expect(children).toEqual(groups.flatMap((g) => g.modules.map((m) => m.id)));
    // Strategy is the Bots item, never a Scanner child.
    expect(children).not.toContain('strategy');
    expect(q('nav-rail-tab-gappers')!.textContent).toMatch(/Gappers/);
  });

  it('shows right-aligned counts from the published dashboard state (99+ capped, zero hidden)', () => {
    render();
    act(() => {
      publishScannerNavState({
        activeTab: 'gappers',
        railHighlight: 'gappers',
        counts: { gappers: 12, gainers: 0, hodMomo: 120 },
      });
    });
    expect(q('nav-rail-tab-gappers')!.querySelector('.nav-rail__count')!.textContent).toBe('12');
    expect(q('nav-rail-tab-gainers')!.querySelector('.nav-rail__count')).toBeNull();
    expect(q('nav-rail-tab-hod_momo')!.querySelector('.nav-rail__count')!.textContent).toBe('99+');
  });

  it('marks the chosen list child active on the Scanner view and the section active', () => {
    render();
    act(() => {
      publishScannerNavState({ activeTab: 'gainers', railHighlight: 'gainers', counts: {} });
    });
    expect(q('nav-rail-scanner')!.classList.contains('is-active')).toBe(true);
    expect(q('nav-rail-tab-gainers')!.classList.contains('is-active')).toBe(true);
    expect(q('nav-rail-tab-gainers')!.getAttribute('aria-current')).toBe('page');
    expect(q('nav-rail-tab-gappers')!.classList.contains('is-active')).toBe(false);
    expect(q('nav-rail')!.getAttribute('data-active-tab')).toBe('gainers');
    expect(q('nav-rail-account')!.classList.contains('is-active')).toBe(false);
  });

  it('marks Account / Bots active from the dashboard tab and Trader while traderActive', () => {
    render();
    act(() => {
      publishScannerNavState({ activeTab: 'trading', railHighlight: 'trading', counts: {} });
    });
    expect(q('nav-rail-account')!.classList.contains('is-active')).toBe(true);
    expect(q('nav-rail-scanner')!.classList.contains('is-active')).toBe(false);
    act(() => {
      publishScannerNavState({ activeTab: 'strategy', railHighlight: 'strategy', counts: {} });
    });
    expect(q('nav-rail-bots')!.classList.contains('is-active')).toBe(true);
    expect(q('nav-rail-account')!.classList.contains('is-active')).toBe(false);

    render({ traderActive: true });
    expect(q('nav-rail-trader')!.classList.contains('is-active')).toBe(true);
    expect(q('nav-rail-trader')!.getAttribute('aria-current')).toBe('page');
    expect(q('nav-rail-bots')!.classList.contains('is-active')).toBe(false);
    expect(q('nav-rail-scanner')!.classList.contains('is-active')).toBe(false);
  });

  it('opens Trader for the selected symbol, SPY when none, and is a no-op while Trader is up', () => {
    render();
    click('nav-rail-trader');
    expect(onOpenTrader).toHaveBeenCalledWith('AAPL');

    workspace.current = { selectedSymbol: null };
    render();
    click('nav-rail-trader');
    expect(onOpenTrader).toHaveBeenLastCalledWith(TRADER_DEFAULT_SYMBOL);

    onOpenTrader.mockReset();
    render({ traderActive: true });
    click('nav-rail-trader');
    expect(onOpenTrader).not.toHaveBeenCalled();
  });

  it('routes a Scanner child through the tab latch and leaves Trader first', () => {
    const seen: string[] = [];
    const onEvent = (e: Event) => seen.push((e as CustomEvent<{ tab: string }>).detail.tab);
    window.addEventListener('nova:nav-rail-select-tab', onEvent);
    render({ traderActive: true });
    // Folded off the Scanner view -- unfold, then pick Gainers.
    click('nav-rail-scanner-chevron');
    click('nav-rail-tab-gainers');
    window.removeEventListener('nova:nav-rail-select-tab', onEvent);
    expect(onLeaveTrader).toHaveBeenCalled();
    expect(seen).toEqual(['gainers']);
    expect(consumeScannerTabRequest()).toBe('gainers');
    expect(getNavPage()).toBe('dashboard');
  });

  it('Account asks for the trading tab, Bots for strategy, Desk and Records switch the shell page', () => {
    render();
    click('nav-rail-account');
    expect(consumeScannerTabRequest()).toBe('trading');
    click('nav-rail-bots');
    expect(consumeScannerTabRequest()).toBe('strategy');
    click('nav-rail-desk');
    expect(getNavPage()).toBe('desk');
    expect(q('nav-rail-desk')!.classList.contains('is-active')).toBe(true);
    expect(onLeaveTrader).not.toHaveBeenCalled();
    click('nav-rail-records');
    expect(getNavPage()).toBe('records');
    expect(q('nav-rail-records')!.classList.contains('is-active')).toBe(true);
    expect(q('nav-rail-desk')!.classList.contains('is-active')).toBe(false);
    // Off the Scanner view the tree is folded; unfold, then a child returns the shell to the dashboard.
    click('nav-rail-scanner-chevron');
    click('nav-rail-tab-losers');
    expect(getNavPage()).toBe('dashboard');
    expect(consumeScannerTabRequest()).toBe('losers');
  });

  it('Scanner from Account returns to the last list shown; on the Scanner view it folds the tree', () => {
    render();
    act(() => {
      publishScannerNavState({ activeTab: 'losers', railHighlight: 'losers', counts: {} });
      publishScannerNavState({ activeTab: 'trading', railHighlight: 'trading', counts: {} });
    });
    click('nav-rail-scanner');
    expect(consumeScannerTabRequest()).toBe('losers');

    act(() => {
      publishScannerNavState({ activeTab: 'losers', railHighlight: 'losers', counts: {} });
    });
    expect(q('nav-rail-scanner-tree')).toBeTruthy();
    click('nav-rail-scanner');
    expect(q('nav-rail-scanner-tree')).toBeNull();
    expect(consumeScannerTabRequest()).toBeNull();
  });

  it('expands the tree on the Scanner view and folds it elsewhere until the operator chooses', () => {
    render();
    expect(q('nav-rail-scanner-tree')).toBeTruthy();
    expect(q('nav-rail-scanner')!.getAttribute('aria-expanded')).toBe('true');
    act(() => {
      setNavPage('desk');
    });
    expect(q('nav-rail-scanner-tree')).toBeNull();
    expect(q('nav-rail')!.classList.contains('nav-rail--folded')).toBe(true);
    expect(localStorage.getItem(NAV_RAIL_STORAGE_KEY)).toBeNull();
  });

  it('persists the fold choice under the versioned key and restores it on remount', () => {
    render();
    click('nav-rail-scanner-chevron');
    expect(q('nav-rail-scanner-tree')).toBeNull();
    const stored = JSON.parse(localStorage.getItem(NAV_RAIL_STORAGE_KEY)!);
    expect(stored).toEqual({ schema_version: NAV_RAIL_SCHEMA_VERSION, collapsed: null, scannerFolded: true });

    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    render();
    expect(q('nav-rail-scanner-tree')).toBeNull();
    click('nav-rail-scanner-chevron');
    expect(q('nav-rail-scanner-tree')).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(NAV_RAIL_STORAGE_KEY)!).scannerFolded).toBe(false);
  });

  it('collapses to the icon-only rail, keeps tooltips, persists, and restores on remount', () => {
    render();
    click('nav-rail-collapse');
    const rail = q('nav-rail')!;
    expect(rail.classList.contains('nav-rail--collapsed')).toBe(true);
    expect(rail.getAttribute('data-collapsed')).toBe('true');
    expect(q('nav-rail-scanner-tree')).toBeNull();
    expect(q('nav-rail-scanner-chevron')).toBeNull();
    expect(q('nav-rail-desk')!.getAttribute('title')).toMatch(/Desk/);
    expect(q('nav-rail-collapse')!.getAttribute('aria-pressed')).toBe('true');
    expect(JSON.parse(localStorage.getItem(NAV_RAIL_STORAGE_KEY)!).collapsed).toBe(true);

    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    render();
    expect(q('nav-rail')!.classList.contains('nav-rail--collapsed')).toBe(true);
    // Collapsed, the Scanner section itself reads active on the Scanner view.
    expect(q('nav-rail-scanner')!.classList.contains('is-active')).toBe(true);
  });

  it('starts collapsed on the Desk and expanded elsewhere until the operator chooses; the choice then wins everywhere', () => {
    render();
    expect(q('nav-rail')!.getAttribute('data-collapsed')).toBe('false');
    act(() => {
      setNavPage('desk');
    });
    expect(q('nav-rail')!.classList.contains('nav-rail--collapsed')).toBe(true);
    expect(q('nav-rail-collapse')!.getAttribute('aria-pressed')).toBe('true');
    // A view default is not a choice: nothing is written.
    expect(localStorage.getItem(NAV_RAIL_STORAGE_KEY)).toBeNull();
    // The full Trader on top of the Desk page is the Trader: labels again.
    render({ traderActive: true });
    expect(q('nav-rail')!.getAttribute('data-collapsed')).toBe('false');
    render({ traderActive: false });
    expect(q('nav-rail')!.getAttribute('data-collapsed')).toBe('true');
    // Expanding on the Desk is a choice that persists and follows the operator to other views.
    click('nav-rail-collapse');
    expect(q('nav-rail')!.getAttribute('data-collapsed')).toBe('false');
    expect(JSON.parse(localStorage.getItem(NAV_RAIL_STORAGE_KEY)!)).toEqual({
      schema_version: NAV_RAIL_SCHEMA_VERSION, collapsed: false, scannerFolded: null,
    });
    act(() => {
      setNavPage('records');
    });
    expect(q('nav-rail')!.getAttribute('data-collapsed')).toBe('false');
    act(() => {
      setNavPage('desk');
    });
    expect(q('nav-rail')!.getAttribute('data-collapsed')).toBe('false');
  });

  it('migrates a v1 payload: collapsed true stays a choice, false becomes "not chosen" so the Desk default applies', () => {
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify({ schema_version: 1, collapsed: false, scannerFolded: true }));
    act(() => {
      setNavPage('desk');
    });
    render();
    expect(q('nav-rail')!.classList.contains('nav-rail--collapsed')).toBe(true);
    expect(q('nav-rail')!.classList.contains('nav-rail--folded')).toBe(true);
    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify({ schema_version: 1, collapsed: true, scannerFolded: false }));
    act(() => {
      setNavPage('dashboard');
    });
    render();
    expect(q('nav-rail')!.classList.contains('nav-rail--collapsed')).toBe(true);
  });

  it('ignores a persisted payload with an unknown schema_version', () => {
    localStorage.setItem(NAV_RAIL_STORAGE_KEY, JSON.stringify({ schema_version: 99, collapsed: true }));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render();
    expect(q('nav-rail')!.classList.contains('nav-rail--collapsed')).toBe(false);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('shows the recording badge on Records while anything is recording', () => {
    status.current = baseStatus({ capture: true, recording: true, capture_symbols: ['GRML', 'IMCC'] });
    render();
    const badge = q('nav-rail-records-badge')!;
    expect(badge).toBeTruthy();
    expect(badge.getAttribute('title')).toBe('2 of 3 recording');
    expect(q('nav-rail-records')!.getAttribute('title')).toMatch(/2 of 3 recording/);

    status.current = baseStatus({ capture: true, recording: false, capture_symbols: [] });
    render();
    expect(q('nav-rail-records-badge')).toBeNull();
  });

  it('keeps Fund account under Account on hover and focus, closes on Escape, and stays reachable offline', () => {
    status.current = baseStatus({ connected: false, mode: 'disconnected' });
    render();
    expect(q('global-bar-fund-account')).toBeNull();
    const wrap = q('nav-rail-account-menu-wrap')!;
    act(() => {
      wrap.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }));
    });
    // React's onMouseEnter listens to mouseover on the root.
    act(() => {
      wrap.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    });
    const menu = q('nav-rail-account-menu')!;
    expect(menu).toBeTruthy();
    expect(menu.querySelector('[data-testid="global-bar-fund-account"]')!.textContent).toBe('Fund account');
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(q('nav-rail-account-menu')).toBeNull();
    act(() => {
      (q('nav-rail-account') as HTMLButtonElement).focus();
    });
    expect(q('global-bar-fund-account')).toBeTruthy();
  });

  it('hides Scanner children, Account and Bots that the Modules setting turned off', () => {
    visibility.current = { gainers: false, trading: false, strategy: false };
    render();
    expect(q('nav-rail-tab-gappers')).toBeTruthy();
    expect(q('nav-rail-tab-gainers')).toBeNull();
    expect(q('nav-rail-account')).toBeNull();
    expect(q('nav-rail-bots')).toBeNull();
  });

  it('Settings toggles the drawer and is absent without a settings API (sample desk)', () => {
    render();
    click('nav-rail-settings');
    expect(toggleSettings).toHaveBeenCalled();
    render({ settings: { open: true, toggle: toggleSettings } });
    expect(q('nav-rail-settings')!.classList.contains('is-active')).toBe(true);
    render({ settings: null });
    expect(q('nav-rail-settings')).toBeNull();
    expect(q('nav-rail-collapse')).toBeTruthy();
  });
});
