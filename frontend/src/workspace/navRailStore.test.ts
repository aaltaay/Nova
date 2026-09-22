/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { NAV_RAIL_SELECT_TAB_EVENT } from '../constantGroups/nav_rail';
import {
  clearScannerNavState,
  consumeScannerTabRequest,
  getNavPage,
  getNavRailSnapshot,
  navRailCollapsedDefault,
  peekScannerTabRequest,
  publishScannerNavState,
  requestScannerTab,
  resetNavRailStoreForTests,
  setNavPage,
} from './navRailStore';

describe('navRailStore', () => {
  beforeEach(() => {
    resetNavRailStoreForTests();
  });

  it('latches a tab request once and routes the shell back to the dashboard', () => {
    setNavPage('records');
    const seen: string[] = [];
    const onEvent = (e: Event) => seen.push((e as CustomEvent<{ tab: string }>).detail.tab);
    window.addEventListener(NAV_RAIL_SELECT_TAB_EVENT, onEvent);
    requestScannerTab('gainers');
    window.removeEventListener(NAV_RAIL_SELECT_TAB_EVENT, onEvent);
    expect(seen).toEqual(['gainers']);
    expect(getNavPage()).toBe('dashboard');
    expect(peekScannerTabRequest()).toBe('gainers');
    expect(consumeScannerTabRequest()).toBe('gainers');
    expect(consumeScannerTabRequest()).toBeNull();
  });

  it('refuses an unknown tab id', () => {
    requestScannerTab('nope' as never);
    expect(peekScannerTabRequest()).toBeNull();
  });

  it('remembers the last Scanner list across Account / Bots and across a dashboard remount', () => {
    publishScannerNavState({ activeTab: 'losers', railHighlight: 'losers', counts: {} });
    expect(getNavRailSnapshot().scanner.lastListTab).toBe('losers');
    publishScannerNavState({ activeTab: 'trading', railHighlight: 'trading', counts: {} });
    publishScannerNavState({ activeTab: 'strategy', railHighlight: 'strategy', counts: {} });
    expect(getNavRailSnapshot().scanner.lastListTab).toBe('losers');
    expect(getNavRailSnapshot().scanner.mounted).toBe(true);
    clearScannerNavState();
    expect(getNavRailSnapshot().scanner.mounted).toBe(false);
    expect(getNavRailSnapshot().scanner.activeTab).toBe('strategy');
    publishScannerNavState({ activeTab: 'trading', railHighlight: 'trading', counts: {} });
    expect(getNavRailSnapshot().scanner.lastListTab).toBe('losers');
  });

  it('collapses the rail to icons on the Desk only, and not while the full Trader is on top of it', () => {
    expect(navRailCollapsedDefault('desk', false)).toBe(true);
    expect(navRailCollapsedDefault('desk', true)).toBe(false);
    expect(navRailCollapsedDefault('dashboard', false)).toBe(false);
    expect(navRailCollapsedDefault('records', false)).toBe(false);
  });

  it('does not emit a new snapshot for an identical publish', () => {
    const counts = { gappers: 1 };
    publishScannerNavState({ activeTab: 'gappers', railHighlight: 'gappers', counts });
    const before = getNavRailSnapshot();
    publishScannerNavState({ activeTab: 'gappers', railHighlight: 'gappers', counts });
    expect(getNavRailSnapshot()).toBe(before);
    publishScannerNavState({ activeTab: 'gappers', railHighlight: 'hod_momo', counts });
    expect(getNavRailSnapshot()).not.toBe(before);
  });
});
